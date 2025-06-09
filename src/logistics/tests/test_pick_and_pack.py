from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

from celery.exceptions import Retry
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
import responses

from campaign.models import (
    Campaign,
    CampaignEmployee,
    DeliveryLocationEnum,
    Employee,
    EmployeeGroup,
    EmployeeGroupCampaign,
    EmployeeGroupCampaignProduct,
    Order,
    OrderProduct,
    Organization,
)
from inventory.models import Brand, Product, ProductBundleItem, Supplier
from logistics.enums import LogisticsCenterEnum, LogisticsCenterMessageTypeEnum
from logistics.models import (
    LogisticsCenterInboundReceipt,
    LogisticsCenterInboundReceiptLine,
    LogisticsCenterInboundStatus,
    LogisticsCenterMessage,
    LogisticsCenterOrderStatus,
    LogisticsCenterStockSnapshot,
    LogisticsCenterStockSnapshotLine,
    PurchaseOrder,
    PurchaseOrderProduct,
)
from logistics.providers.pick_and_pack import (
    _platform_id_to_pap_id,
    add_or_update_inbound as pick_and_pack_add_or_update_inbound,
    add_or_update_outbound as pick_and_pack_add_or_update_outbound,
)
from logistics.tasks import (
    process_logistics_center_message,
    send_order_to_logistics_center,
)


@override_settings(
    PAP_INBOUND_URL='https://test.local/inbound',
    PAP_OUTBOUND_URL='https://test.local/outbound',
    PAP_CONSIGNEE='AAA',
)
class PickAndPackProviderTestCase(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(
            name='supplier name',
        )
        self.brand = Brand.objects.create(
            name='brand name',
        )
        self.product_1 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name_en='product 1 name en',
            sku='1',
            reference='1231231231231',
            cost_price=50,
            sale_price=60,
        )
        self.product_2 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 2 name',
            sku='2',
            cost_price=70,
            sale_price=80,
        )
        self.purchase_order_1 = PurchaseOrder.objects.create(supplier=self.supplier)
        PurchaseOrderProduct.objects.create(
            product_id=self.product_1,
            purchase_order=self.purchase_order_1,
            quantity_ordered=1,
            quantity_sent_to_logistics_center=0,
        )
        self.purchase_order_2 = PurchaseOrder.objects.create(supplier=self.supplier)
        PurchaseOrderProduct.objects.create(
            product_id=self.product_1,
            purchase_order=self.purchase_order_2,
            quantity_ordered=2,
            quantity_sent_to_logistics_center=0,
        )
        PurchaseOrderProduct.objects.create(
            product_id=self.product_2,
            purchase_order=self.purchase_order_2,
            quantity_ordered=3,
            quantity_sent_to_logistics_center=0,
        )

        # create the campaign infrastructure for the orders we need
        self.organization = Organization.objects.create(
            name='Test organization',
            manager_full_name='Test manager',
            manager_phone_number='0500000009',
            manager_email='manager@test.test',
        )
        campaign = Campaign.objects.create(
            name='Test campaign',
            organization=self.organization,
            status=Campaign.CampaignStatusEnum.ACTIVE.name,
            start_date_time=datetime.now(),
            end_date_time=datetime.now(),
        )
        self.employee_group_1 = EmployeeGroup.objects.create(
            name='Test employee group 1',
            organization=self.organization,
            delivery_city='Office1',
            delivery_street='Office street 1',
            delivery_street_number='1',
            delivery_apartment_number='2',
            delivery_location=DeliveryLocationEnum.ToHome.name,
        )
        self.employee_group_2 = EmployeeGroup.objects.create(
            name='Test employee group 2',
            organization=self.organization,
            delivery_city='Office2',
            delivery_street='Office street 2',
            delivery_street_number='3',
            delivery_apartment_number='4',
            delivery_location=DeliveryLocationEnum.ToOffice.name,
        )
        employee_group_campaign_1 = EmployeeGroupCampaign.objects.create(
            employee_group=self.employee_group_1,
            campaign=campaign,
            budget_per_employee=100,
        )
        self.employee_group_campaign_2 = EmployeeGroupCampaign.objects.create(
            employee_group=self.employee_group_2,
            campaign=campaign,
            budget_per_employee=100,
        )
        self.employee_1 = Employee.objects.create(
            employee_group=self.employee_group_1,
            first_name='Test',
            last_name='Employee 1',
            email='test1@test.test',
        )
        self.employee_2 = Employee.objects.create(
            employee_group=self.employee_group_2,
            first_name='Test',
            last_name='Employee 2',
            email='test2@test.test',
        )
        employee_group_1_campaign_product_1 = (
            EmployeeGroupCampaignProduct.objects.create(
                employee_group_campaign_id=employee_group_campaign_1,
                product_id=self.product_1,
            )
        )
        employee_group_1_campaign_product_2 = (
            EmployeeGroupCampaignProduct.objects.create(
                employee_group_campaign_id=employee_group_campaign_1,
                product_id=self.product_2,
            )
        )
        employee_group_2_campaign_product_1 = (
            EmployeeGroupCampaignProduct.objects.create(
                employee_group_campaign_id=self.employee_group_campaign_2,
                product_id=self.product_1,
            )
        )

        # the orders we need for testing outbound
        self.order_1 = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=self.employee_1
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 1',
            phone_number='0500000000',
            additional_phone_number='050000001',
            delivery_city='City1',
            delivery_street='Main1',
            delivery_street_number='1',
            delivery_apartment_number='1',
            delivery_additional_details='Additional 1',
        )
        OrderProduct.objects.create(
            order_id=self.order_1,
            product_id=employee_group_1_campaign_product_1,
            quantity=1,
        )
        self.order_2 = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=self.employee_1
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 2',
            phone_number='0500000002',
            additional_phone_number='050000003',
            delivery_city='City2',
            delivery_street='Main2',
            delivery_street_number='2',
            delivery_apartment_number='2',
            delivery_additional_details='Additional 2',
        )
        OrderProduct.objects.create(
            order_id=self.order_2,
            product_id=employee_group_1_campaign_product_1,
            quantity=2,
        )
        OrderProduct.objects.create(
            order_id=self.order_2,
            product_id=employee_group_1_campaign_product_2,
            quantity=3,
        )
        self.order_3 = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=self.employee_2
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 3',
            phone_number='0500000004',
            additional_phone_number='050000005',
            delivery_city='City3',
            delivery_street='Main3',
            delivery_street_number='3',
            delivery_apartment_number='3',
            delivery_additional_details='Additional 3',
        )
        OrderProduct.objects.create(
            order_id=self.order_3,
            product_id=employee_group_2_campaign_product_1,
            quantity=4,
        )

    @responses.activate
    def test_add_or_update_inbound_failure(self):
        responses.add(
            responses.POST,
            settings.PAP_INBOUND_URL,
            json={},
            status=400,
        )

        result = pick_and_pack_add_or_update_inbound(
            self.purchase_order_1, datetime.now()
        )

        # result should be false since the mock api responded with an error
        self.assertEquals(result, False)

    @responses.activate
    def test_add_or_update_inbound_success(self):
        responses.add(
            responses.POST,
            settings.PAP_INBOUND_URL,
            json={},
            status=200,
        )

        result = pick_and_pack_add_or_update_inbound(
            self.purchase_order_1, datetime.now()
        )

        # result should be true since we succeeded
        self.assertEquals(result, True)

        # check that the body sent to the api contains the single product
        api_request_lines = json.loads(responses.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 1)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)

    @responses.activate
    def test_add_or_update_inbound_success_multiple_products(self):
        responses.add(
            responses.POST,
            settings.PAP_INBOUND_URL,
            json={},
            status=200,
        )

        result = pick_and_pack_add_or_update_inbound(
            self.purchase_order_2, datetime.now()
        )

        # result should be true since we succeeded
        self.assertEquals(result, True)

        # check that the body sent to the api contains the two products
        api_request_lines = json.loads(responses.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 2)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)
        self.assertEquals(api_request_lines[1]['SKU'], self.product_2.sku)

    @responses.activate
    def test_add_or_update_outbound_failure(self):
        responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=400,
        )

        # fetch the order so manager annotated fields are included
        order = Order.objects.get(pk=self.order_1.pk)
        result = pick_and_pack_add_or_update_outbound(
            order,
            order.ordered_products(),
            datetime.now(),
        )

        # result should be false since the mock api responded with an error
        self.assertEquals(result, False)

    @responses.activate
    def test_add_or_update_outbound_success(self):
        responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=200,
        )

        # fetch the order so manager annotated fields are included
        order = Order.objects.get(pk=self.order_1.pk)
        result = pick_and_pack_add_or_update_outbound(
            order,
            order.ordered_products(),
            datetime.now(),
        )

        # result should be true since we succeeded
        self.assertEquals(result, True)

        api_request_body_json = json.loads(responses.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']

        # check that the reference order value sent to the api is correct
        api_reference_order = api_request_body_json['REFERENCEORD']
        self.assertEquals(api_reference_order, '')

        # check the the contact details sent to the api are correct
        api_request_contact = api_request_body_json['CONTACT']
        self.assertEquals(
            api_request_contact['STREET1'],
            f'{self.order_1.delivery_street} {self.order_1.delivery_street_number}',
        )
        self.assertEquals(
            api_request_contact['STREET2'],
            f'דירה {self.order_1.delivery_apartment_number}',
        )
        self.assertEquals(api_request_contact['CITY'], self.order_1.delivery_city)
        self.assertEquals(api_request_contact['CONTACT1NAME'], self.order_1.full_name)
        self.assertEquals(api_request_contact['CONTACT2NAME'], self.order_1.full_name)
        self.assertEquals(
            api_request_contact['CONTACT1PHONE'], self.order_1.phone_number
        )
        self.assertEquals(
            api_request_contact['CONTACT2PHONE'],
            self.order_1.additional_phone_number,
        )
        self.assertEquals(api_request_contact['CONTACT1EMAIL'], self.employee_1.email)
        self.assertEquals(api_request_contact['CONTACT2EMAIL'], '')

        # check that the address sent to the api is the order's address
        api_shipping_details = api_request_body_json['SHIPPINGDETAIL']
        self.assertEquals(
            api_shipping_details['DELIVERYCOMMENTS'],
            self.order_1.delivery_additional_details,
        )

        # check that no bundles were sent to the api
        self.assertEquals(api_request_body_json['BUNDLE'], '')

        # check that the lines sent to the api contain the single product
        api_request_lines = api_request_body_json['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 1)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)
        self.assertEquals(
            api_request_lines[0]['QTYORIGINAL'],
            self.order_1.ordered_products()[0]['quantity'],
        )

    @responses.activate
    def test_add_or_update_outbound_success_multiple_products(self):
        responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=200,
        )

        # fetch the order so manager annotated fields are included
        order = Order.objects.get(pk=self.order_2.pk)
        result = pick_and_pack_add_or_update_outbound(
            order,
            order.ordered_products(),
            datetime.now(),
        )

        # result should be true since we succeeded
        self.assertEquals(result, True)

        api_request_body_json = json.loads(responses.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']

        # check that the reference order value sent to the api is correct
        api_reference_order = api_request_body_json['REFERENCEORD']
        self.assertEquals(api_reference_order, '')

        # check the the contact details sent to the api are correct
        api_request_contact = api_request_body_json['CONTACT']
        self.assertEquals(
            api_request_contact['STREET1'],
            f'{self.order_2.delivery_street} {self.order_2.delivery_street_number}',
        )
        self.assertEquals(
            api_request_contact['STREET2'],
            f'דירה {self.order_2.delivery_apartment_number}',
        )
        self.assertEquals(api_request_contact['CITY'], self.order_2.delivery_city)
        self.assertEquals(api_request_contact['CONTACT1NAME'], self.order_2.full_name)
        self.assertEquals(api_request_contact['CONTACT2NAME'], self.order_2.full_name)
        self.assertEquals(
            api_request_contact['CONTACT1PHONE'], self.order_2.phone_number
        )
        self.assertEquals(
            api_request_contact['CONTACT2PHONE'],
            self.order_2.additional_phone_number,
        )
        self.assertEquals(api_request_contact['CONTACT1EMAIL'], self.employee_1.email)
        self.assertEquals(api_request_contact['CONTACT2EMAIL'], '')

        # check that the address sent to the api is the order's address
        api_shipping_details = api_request_body_json['SHIPPINGDETAIL']
        self.assertEquals(
            api_shipping_details['DELIVERYCOMMENTS'],
            self.order_2.delivery_additional_details,
        )

        # check that no bundles were sent to the api
        self.assertEquals(api_request_body_json['BUNDLE'], '')

        # check that the lines sent to the api contain the single product
        api_request_lines = api_request_body_json['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 2)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)
        self.assertEquals(
            api_request_lines[0]['QTYORIGINAL'],
            self.order_2.ordered_products()[0]['quantity'],
        )
        self.assertEquals(api_request_lines[1]['SKU'], self.product_2.sku)
        self.assertEquals(
            api_request_lines[1]['QTYORIGINAL'],
            self.order_2.ordered_products()[1]['quantity'],
        )

    @responses.activate
    def test_add_or_update_outbound_success_office_delivery(self):
        responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=200,
        )

        # fetch the order so manager annotated fields are included
        order = Order.objects.get(pk=self.order_3.pk)
        result = pick_and_pack_add_or_update_outbound(
            order,
            order.ordered_products(),
            datetime.now(),
        )

        # result should be true since we succeeded
        self.assertEquals(result, True)

        api_request_body_json = json.loads(responses.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']

        # check that the reference order value sent to the api is correct
        api_reference_order = api_request_body_json['REFERENCEORD']
        self.assertEquals(
            api_reference_order,
            _platform_id_to_pap_id(self.employee_group_campaign_2.pk),
        )

        # check the the contact details sent to the api are correct - since
        # this employee is in an office-delivery group the address should be
        # that of the office
        api_request_contact = api_request_body_json['CONTACT']
        self.assertEquals(
            api_request_contact['STREET1'],
            (
                f'{self.employee_group_2.delivery_street} '
                f'{self.employee_group_2.delivery_street_number}'
            ),
        )
        self.assertEquals(
            api_request_contact['STREET2'],
            f'דירה {self.employee_group_2.delivery_apartment_number}',
        )
        self.assertEquals(
            api_request_contact['CITY'], self.employee_group_2.delivery_city
        )
        self.assertEquals(
            api_request_contact['CONTACT1NAME'], self.employee_2.full_name
        )
        self.assertEquals(
            api_request_contact['CONTACT2NAME'], self.organization.manager_full_name
        )
        self.assertEquals(
            api_request_contact['CONTACT1PHONE'], self.employee_2.phone_number
        )
        self.assertEquals(
            api_request_contact['CONTACT2PHONE'],
            self.organization.manager_phone_number,
        )
        self.assertEquals(api_request_contact['CONTACT1EMAIL'], self.employee_2.email)
        self.assertEquals(
            api_request_contact['CONTACT2EMAIL'],
            self.organization.manager_email,
        )

        # check that the address sent to the api is the order's address
        api_shipping_details = api_request_body_json['SHIPPINGDETAIL']
        self.assertEquals(
            api_shipping_details['DELIVERYCOMMENTS'],
            '',
        )

        # check that no bundles were sent to the api
        self.assertEquals(api_request_body_json['BUNDLE'], '')

        # check that the lines sent to the api contain the single product
        api_request_lines = api_request_body_json['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 1)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)
        self.assertEquals(
            api_request_lines[0]['QTYORIGINAL'],
            self.order_3.ordered_products()[0]['quantity'],
        )


@override_settings(
    PAP_INBOUND_URL='https://test.local/inbound',
    PAP_OUTBOUND_URL='https://test.local/outbound',
    PAP_CONSIGNEE='AAA',
    ACTIVE_LOGISTICS_CENTER=LogisticsCenterEnum.PICK_AND_PACK,
)
class SendPurchaseOrderToLogisticsCenterTestCase(TestCase):
    def setUp(self):
        self.supplier_1 = Supplier.objects.create(
            name='supplier name',
        )
        self.supplier_2 = Supplier.objects.create(
            name='supplier "name"',
        )
        self.brand = Brand.objects.create(
            name='brand name',
        )
        self.product_1 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier_1,
            name='product 1 name',
            sku='1',
            cost_price=50,
            sale_price=60,
        )
        product_2 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier_2,
            name='product "2" name',
            sku='2',
            cost_price=50,
            sale_price=60,
        )
        self.purchase_order_1 = PurchaseOrder.objects.create(supplier=self.supplier_1)
        PurchaseOrderProduct.objects.create(
            product_id=self.product_1,
            purchase_order=self.purchase_order_1,
            quantity_ordered=1,
            quantity_sent_to_logistics_center=0,
        )
        self.purchase_order_2 = PurchaseOrder.objects.create(supplier=self.supplier_2)
        PurchaseOrderProduct.objects.create(
            product_id=product_2,
            purchase_order=self.purchase_order_2,
            quantity_ordered=1,
            quantity_sent_to_logistics_center=0,
        )

    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    @patch('logistics.tasks.pick_and_pack_add_or_update_inbound', return_value=True)
    def test_task_triggered_on_purchase_order_approve(self, mock_update_inbound):
        # mock is not called to begin with
        self.assertEquals(mock_update_inbound.call_count, 0)

        # we can take an existing purchase order and change its status to
        # anything but approved, or create a new purchase order with any status
        # besided approved and the task should not be invoked
        self.purchase_order_1.status = PurchaseOrder.Status.PENDING.name
        self.purchase_order_1.save()
        self.purchase_order_1.status = PurchaseOrder.Status.SENT_TO_SUPPLIER.name
        self.purchase_order_1.save()
        self.purchase_order_1.status = PurchaseOrder.Status.CANCELLED.name
        self.purchase_order_1.save()
        PurchaseOrder.objects.create(supplier=self.supplier_1)
        PurchaseOrder.objects.create(
            supplier=self.supplier_1,
            status=PurchaseOrder.Status.PENDING.name,
        )
        PurchaseOrder.objects.create(
            supplier=self.supplier_1,
            status=PurchaseOrder.Status.SENT_TO_SUPPLIER.name,
        )
        PurchaseOrder.objects.create(
            supplier=self.supplier_1,
            status=PurchaseOrder.Status.CANCELLED.name,
        )

        # mock was not yet called
        self.assertEquals(mock_update_inbound.call_count, 0)

        # update an existing purchase order's status to approved and the task
        # should be invoked
        self.purchase_order_1.approve()

        # mock was called
        self.assertEquals(mock_update_inbound.call_count, 1)
        self.assertEquals(
            mock_update_inbound.call_args[0][0],
            self.purchase_order_1,
        )

        self.purchase_order_1.refresh_from_db()

        # approving a purchase order again should raise a validation error
        with self.assertRaises(ValidationError):
            self.purchase_order_1.approve()

        # mock was not called again
        self.assertEquals(mock_update_inbound.call_count, 1)

    @responses.activate
    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_task_api_calls(self):
        inbound_api_mock = responses.add(
            responses.POST,
            settings.PAP_INBOUND_URL,
            json={},
            status=200,
        )

        # the sent_to_logistics_center_at field should be None
        self.purchase_order_1.refresh_from_db()
        self.assertEquals(self.purchase_order_1.sent_to_logistics_center_at, None)

        self.purchase_order_1.approve()

        # each mock should have been called once
        self.assertEquals(len(inbound_api_mock.calls), 1)

        # the sent_to_logistics_center_at field was set and is within the last
        # 5 seconds
        self.purchase_order_1.refresh_from_db()
        self.assertGreaterEqual(
            self.purchase_order_1.sent_to_logistics_center_at,
            datetime.now(timezone.utc) - timedelta(seconds=5),
        )

    @responses.activate
    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_purchase_order_fields_with_quotes(self):
        inbound_api_mock = responses.add(
            responses.POST,
            settings.PAP_INBOUND_URL,
            json={},
            status=200,
        )

        self.purchase_order_2.approve()

        # each mock should have been called once
        self.assertEquals(len(inbound_api_mock.calls), 1)

        # the request body should contain no quotes, even though the order and
        # product objects did contain them
        json_request_body = json.loads(inbound_api_mock.calls[0].request.body)
        json_request_data = json_request_body['DATACOLLECTION']['DATA']
        self.assertEquals(json_request_data['SOURCECOMPANY'], 'supplier name')
        self.assertEquals(
            json_request_data['LINES'],
            {
                'LINE': [
                    {
                        'ORDERLINE': 0,
                        'REFERENCEORDLINE': 0,
                        'SKU': '2',
                        'QTYORDERED': 1,
                        'INVENTORYSTATUS': 'AVAILABLE',
                        'SKUDESCRIPTION': 'product 2 name',
                        'MANUFACTURERSKU': None,
                    },
                ],
            },
        )


@override_settings(
    PAP_INBOUND_URL='https://test.local/inbound',
    PAP_OUTBOUND_URL='https://test.local/outbound',
    PAP_CONSIGNEE='AAA',
    ACTIVE_LOGISTICS_CENTER=LogisticsCenterEnum.PICK_AND_PACK,
)
class SendOrderToLogisticsCenterTestCase(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(
            name='supplier name',
        )
        self.brand = Brand.objects.create(
            name='brand name',
        )
        self.product_1 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 1 name',
            sku='1',
            cost_price=50,
            sale_price=60,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.PHYSICAL.name,
        )
        self.product_2 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 2 name',
            sku='2',
            cost_price=70,
            sale_price=80,
            product_type=Product.ProductTypeEnum.SENT_BY_SUPPLIER.name,
            product_kind=Product.ProductKindEnum.PHYSICAL.name,
        )
        self.product_3 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 3 name',
            sku='3',
            cost_price=90,
            sale_price=100,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.MONEY.name,
        )

        self.product_4 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 4 name',
            sku='4',
            cost_price=110,
            sale_price=120,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.PHYSICAL.name,
        )
        self.product_5 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 5 name',
            sku='5',
            cost_price=130,
            sale_price=140,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.PHYSICAL.name,
        )
        # a bundle product
        self.product_6 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 6 name',
            sku='4|1,5|2',
            cost_price=150,
            sale_price=160,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.BUNDLE.name,
        )
        ProductBundleItem.objects.create(
            bundle=self.product_6,
            product=self.product_4,
            quantity=1,
        )
        ProductBundleItem.objects.create(
            bundle=self.product_6,
            product=self.product_5,
            quantity=2,
        )
        # a second bundle product
        self.product_7 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 7 name',
            sku='1|3,5|2',
            cost_price=150,
            sale_price=160,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.BUNDLE.name,
        )
        ProductBundleItem.objects.create(
            bundle=self.product_7,
            product=self.product_1,
            quantity=3,
        )
        ProductBundleItem.objects.create(
            bundle=self.product_7,
            product=self.product_5,
            quantity=2,
        )
        # a product with quotes
        self.product_8 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product "8" name',
            sku='8',
            cost_price=150,
            sale_price=160,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.PHYSICAL.name,
        )

        # create the campaign infrastructure for the orders we need
        organization = Organization.objects.create(
            name='Test organization',
            manager_full_name='Test manager',
            manager_phone_number='0500000009',
            manager_email='manager@test.test',
        )
        campaign = Campaign.objects.create(
            name='Test campaign',
            organization=organization,
            status=Campaign.CampaignStatusEnum.ACTIVE.name,
            start_date_time=datetime.now(),
            end_date_time=datetime.now(),
        )
        employee_group = EmployeeGroup.objects.create(
            name='Test employee group 1',
            organization=organization,
            delivery_city='Office1',
            delivery_street='Office street 1',
            delivery_street_number='1',
            delivery_apartment_number='2',
            delivery_location=DeliveryLocationEnum.ToHome.name,
        )
        employee_group_campaign = EmployeeGroupCampaign.objects.create(
            employee_group=employee_group, campaign=campaign, budget_per_employee=100
        )
        employee = Employee.objects.create(
            employee_group=employee_group,
            first_name='Test',
            last_name='Employee 1',
            email='test1@test.test',
        )
        self.employee_group_campaign_product_1 = (
            EmployeeGroupCampaignProduct.objects.create(
                employee_group_campaign_id=employee_group_campaign,
                product_id=self.product_1,
            )
        )
        employee_group_campaign_product_2 = EmployeeGroupCampaignProduct.objects.create(
            employee_group_campaign_id=employee_group_campaign,
            product_id=self.product_2,
        )
        employee_group_campaign_product_3 = EmployeeGroupCampaignProduct.objects.create(
            employee_group_campaign_id=employee_group_campaign,
            product_id=self.product_3,
        )
        employee_group_campaign_product_6 = EmployeeGroupCampaignProduct.objects.create(
            employee_group_campaign_id=employee_group_campaign,
            product_id=self.product_6,
        )
        employee_group_campaign_product_7 = EmployeeGroupCampaignProduct.objects.create(
            employee_group_campaign_id=employee_group_campaign,
            product_id=self.product_7,
        )
        employee_group_campaign_product_8 = EmployeeGroupCampaignProduct.objects.create(
            employee_group_campaign_id=employee_group_campaign,
            product_id=self.product_8,
        )

        # the order we need for testing outbound
        self.order = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=employee
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 1',
            phone_number='0500000000',
            additional_phone_number='050000001',
            delivery_city='City1',
            delivery_street='Main1',
            delivery_street_number='1',
            delivery_apartment_number='1',
            delivery_additional_details='Additional 1',
        )
        OrderProduct.objects.create(
            order_id=self.order,
            product_id=self.employee_group_campaign_product_1,
            quantity=1,
        )

        # another order with sent-by-supplier and money products
        self.order_2 = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=employee
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 1',
            phone_number='0500000000',
            additional_phone_number='050000001',
            delivery_city='City1',
            delivery_street='Main1',
            delivery_street_number='1',
            delivery_apartment_number='1',
            delivery_additional_details='Additional 1',
        )
        OrderProduct.objects.create(
            order_id=self.order_2,
            product_id=employee_group_campaign_product_2,
            quantity=1,
        )
        OrderProduct.objects.create(
            order_id=self.order_2,
            product_id=employee_group_campaign_product_3,
            quantity=1,
        )

        # another order with normal and bundle items
        self.order_3 = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=employee
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 1',
            phone_number='0500000000',
            additional_phone_number='050000001',
            delivery_city='City1',
            delivery_street='Main1',
            delivery_street_number='1',
            delivery_apartment_number='1',
            delivery_additional_details='Additional 1',
        )
        OrderProduct.objects.create(
            order_id=self.order_3,
            product_id=self.employee_group_campaign_product_1,
            quantity=1,
        )
        OrderProduct.objects.create(
            order_id=self.order_3,
            product_id=employee_group_campaign_product_6,
            quantity=2,
        )

        # an order with normal and multiple bundle items
        self.order_4 = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=employee
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 4',
            phone_number='0500000000',
            additional_phone_number='050000001',
            delivery_city='City4',
            delivery_street='Main4',
            delivery_street_number='4',
            delivery_apartment_number='4',
            delivery_additional_details='Additional 4',
        )
        OrderProduct.objects.create(
            order_id=self.order_4,
            product_id=self.employee_group_campaign_product_1,
            quantity=1,
        )
        OrderProduct.objects.create(
            order_id=self.order_4,
            product_id=employee_group_campaign_product_6,
            quantity=1,
        )
        OrderProduct.objects.create(
            order_id=self.order_4,
            product_id=employee_group_campaign_product_7,
            quantity=2,
        )

        # an order with lots of bundle items that can break the 120 character
        # limit
        self.order_5 = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=employee
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 5',
            phone_number='0500000000',
            additional_phone_number='050000001',
            delivery_city='City5',
            delivery_street='Main5',
            delivery_street_number='5',
            delivery_apartment_number='5',
            delivery_additional_details='Additional 5',
        )
        OrderProduct.objects.create(
            order_id=self.order_5,
            product_id=employee_group_campaign_product_7,
            quantity=20,
        )

        # an order with quotes everywhere
        self.order_6 = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=employee
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test "name" 6',
            phone_number='050000"0006',
            additional_phone_number='050"000007',
            delivery_city='City"6',
            delivery_street='Main"6',
            delivery_street_number='"6',
            delivery_apartment_number='6"',
            delivery_additional_details='Ad"ditional" 6',
        )
        OrderProduct.objects.create(
            order_id=self.order_6,
            product_id=employee_group_campaign_product_8,
            quantity=1,
        )

    @responses.activate
    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_task_api_calls(self):
        outbound_api_mock = responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=200,
        )

        # the status field should be pending
        self.order.refresh_from_db()
        self.assertEquals(self.order.status, Order.OrderStatusEnum.PENDING.name)

        send_order_to_logistics_center.apply_async(
            (self.order.pk, LogisticsCenterEnum.PICK_AND_PACK)
        )

        # each mock should have been called once
        self.assertEquals(len(outbound_api_mock.calls), 1)

        # the status field was set to sent to logistics center
        self.order.refresh_from_db()
        self.assertEquals(
            self.order.status,
            Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
        )

    @responses.activate
    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_ignore_order_products_sent_by_supplier_money(self):
        outbound_api_mock = responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=200,
        )

        # the status field should be pending
        self.order_2.refresh_from_db()
        self.assertEquals(self.order_2.status, Order.OrderStatusEnum.PENDING.name)

        send_order_to_logistics_center.apply_async(
            (self.order_2.pk, LogisticsCenterEnum.PICK_AND_PACK)
        )

        # mocks should not have been called since no order product should be
        # sent to the logistics provider
        self.assertEquals(len(outbound_api_mock.calls), 0)

        # the status field should still be pending
        self.order_2.refresh_from_db()
        self.assertEquals(self.order_2.status, Order.OrderStatusEnum.PENDING.name)

        # add a regular physical product to the order
        OrderProduct.objects.create(
            order_id=self.order_2,
            product_id=self.employee_group_campaign_product_1,
            quantity=1,
        )
        self.order_2.refresh_from_db()

        send_order_to_logistics_center.apply_async(
            (self.order_2.pk, LogisticsCenterEnum.PICK_AND_PACK)
        )

        # each mock should have been called once now
        self.assertEquals(len(outbound_api_mock.calls), 1)

        # the status field was set to sent to logistics center
        self.order_2.refresh_from_db()
        self.assertEquals(
            self.order_2.status,
            Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
        )

        # no bundles should have been sent to the provider
        self.assertEquals(
            json.loads(outbound_api_mock.calls[0].request.body)['DATACOLLECTION'][
                'DATA'
            ]['BUNDLE'],
            '',
        )

        # only the regular physical product should have been sent to the
        # provider
        api_request_lines = json.loads(outbound_api_mock.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 1)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)

    @responses.activate
    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_order_bundle_products(self):
        outbound_api_mock = responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=200,
        )

        # the status field should be pending
        self.order_3.refresh_from_db()
        self.assertEquals(self.order_3.status, Order.OrderStatusEnum.PENDING.name)

        send_order_to_logistics_center.apply_async(
            (self.order_3.pk, LogisticsCenterEnum.PICK_AND_PACK)
        )

        # each mock should have been called once
        self.assertEquals(len(outbound_api_mock.calls), 1)

        # the status field was set to sent to logistics center
        self.order_3.refresh_from_db()
        self.assertEquals(
            self.order_3.status,
            Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
        )

        # bundle skus should have been sent to the provider
        self.assertEquals(
            json.loads(outbound_api_mock.calls[0].request.body)['DATACOLLECTION'][
                'DATA'
            ]['BUNDLE'],
            '4|1,5|2|||4|1,5|2',
        )

        # bundled products should have been sent and not the bundle product
        api_request_lines = json.loads(outbound_api_mock.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 3)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)
        self.assertEquals(api_request_lines[0]['QTYORIGINAL'], 1)
        self.assertEquals(api_request_lines[1]['SKU'], self.product_4.sku)
        self.assertEquals(api_request_lines[1]['QTYORIGINAL'], 2)
        self.assertEquals(api_request_lines[2]['SKU'], self.product_5.sku)
        self.assertEquals(api_request_lines[2]['QTYORIGINAL'], 4)

    @responses.activate
    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_order_multiple_bundles_and_other_products(self):
        outbound_api_mock = responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=200,
        )

        # the status field should be pending
        self.order_4.refresh_from_db()
        self.assertEquals(self.order_4.status, Order.OrderStatusEnum.PENDING.name)

        send_order_to_logistics_center.apply_async(
            (self.order_4.pk, LogisticsCenterEnum.PICK_AND_PACK)
        )

        # each mock should have been called once
        self.assertEquals(len(outbound_api_mock.calls), 1)

        # the status field was set to sent to logistics center
        self.order_4.refresh_from_db()
        self.assertEquals(
            self.order_4.status,
            Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
        )

        # bundle skus should have been sent to the provider
        self.assertEquals(
            json.loads(outbound_api_mock.calls[0].request.body)['DATACOLLECTION'][
                'DATA'
            ]['BUNDLE'],
            '4|1,5|2|||1|3,5|2|||1|3,5|2',
        )

        # bundled products should have been sent and not the bundle product
        api_request_lines = json.loads(outbound_api_mock.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 5)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)
        self.assertEquals(api_request_lines[0]['QTYORIGINAL'], 1)
        self.assertEquals(api_request_lines[1]['SKU'], self.product_4.sku)
        self.assertEquals(api_request_lines[1]['QTYORIGINAL'], 1)
        self.assertEquals(api_request_lines[2]['SKU'], self.product_5.sku)
        self.assertEquals(api_request_lines[2]['QTYORIGINAL'], 2)
        self.assertEquals(api_request_lines[3]['SKU'], self.product_1.sku)
        self.assertEquals(api_request_lines[3]['QTYORIGINAL'], 6)
        self.assertEquals(api_request_lines[4]['SKU'], self.product_5.sku)
        self.assertEquals(api_request_lines[4]['QTYORIGINAL'], 4)

    @responses.activate
    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_order_long_bundle_string(self):
        outbound_api_mock = responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=200,
        )

        # the status field should be pending
        self.order_5.refresh_from_db()
        self.assertEquals(self.order_5.status, Order.OrderStatusEnum.PENDING.name)

        send_order_to_logistics_center.apply_async(
            (self.order_5.pk, LogisticsCenterEnum.PICK_AND_PACK)
        )

        # each mock should have been called once
        self.assertEquals(len(outbound_api_mock.calls), 1)

        # the status field was set to sent to logistics center
        self.order_5.refresh_from_db()
        self.assertEquals(
            self.order_5.status,
            Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
        )

        # bundle skus should have been sent to the provider, but shortened to
        # 120 characters
        self.assertEquals(
            json.loads(outbound_api_mock.calls[0].request.body)['DATACOLLECTION'][
                'DATA'
            ]['BUNDLE'],
            '1|3,5|2|||1|3,5|2|||1|3,5|2|||1|3,5|2|||1|3,5|2|||1|3,5|2|||1|3,5|2|||1|3,5|2|||1|3,5|2|||1|3,5|2|||1|3,5|2|||1|3,5|2|||',
        )

        # bundled products should have been sent and not the bundle product
        api_request_lines = json.loads(outbound_api_mock.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 2)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)
        self.assertEquals(api_request_lines[0]['QTYORIGINAL'], 60)
        self.assertEquals(api_request_lines[1]['SKU'], self.product_5.sku)
        self.assertEquals(api_request_lines[1]['QTYORIGINAL'], 40)

    @responses.activate
    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_order_fields_with_quotes(self):
        outbound_api_mock = responses.add(
            responses.POST,
            settings.PAP_OUTBOUND_URL,
            json={},
            status=200,
        )

        send_order_to_logistics_center.apply_async(
            (self.order_6.pk, LogisticsCenterEnum.PICK_AND_PACK)
        )

        # each mock should have been called once
        self.assertEquals(len(outbound_api_mock.calls), 1)

        # the request body should contain no quotes, even though the order and
        # product objects did contain them
        json_request_body = json.loads(outbound_api_mock.calls[0].request.body)
        json_request_data = json_request_body['DATACOLLECTION']['DATA']
        self.assertEquals(
            json_request_data['CONTACT'],
            {
                'STREET1': 'Main6 6',
                'STREET2': 'דירה 6',
                'CITY': 'City6',
                'CONTACT1NAME': 'Test name 6',
                'CONTACT2NAME': 'Test name 6',
                'CONTACT1PHONE': '0500000006',
                'CONTACT2PHONE': '050000007',
                'CONTACT1EMAIL': 'test1@test.test',
                'CONTACT2EMAIL': '',
            },
        )
        self.assertEquals(
            json_request_data['SHIPPINGDETAIL'],
            {'DELIVERYCOMMENTS': 'Additional 6'},
        )
        self.assertEquals(
            json_request_data['LINES'],
            {
                'LINE': [
                    {
                        'ORDERLINE': 0,
                        'REFERENCEORDLINE': 0,
                        'SKU': '8',
                        'QTYORIGINAL': 1,
                        'INVENTORYSTATUS': 'AVAILABLE',
                        'SKUDESCRIPTION': 'product 8 name',
                        'MANUFACTURERSKU': None,
                    },
                ],
            },
        )


class ProcessLogisticsCenterInboundStatusChangeMessageTestCase(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(
            name='supplier name',
        )
        self.brand = Brand.objects.create(
            name='brand name',
        )
        self.product_1 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 1 name',
            sku='1',
            cost_price=50,
            sale_price=60,
        )
        self.purchase_order_1 = PurchaseOrder.objects.create(
            supplier=self.supplier,
            logistics_center=LogisticsCenterEnum.PICK_AND_PACK.name,
            logistics_center_id='1000',
        )
        self.purchase_order_product_1 = PurchaseOrderProduct.objects.create(
            product_id=self.product_1,
            purchase_order=self.purchase_order_1,
            quantity_ordered=1,
            quantity_sent_to_logistics_center=0,
        )

        self.logistics_center_message_invalid_1 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.INBOUND_STATUS_CHANGE.name,
            raw_body='{}',
        )
        self.logistics_center_message_invalid_2 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.INBOUND_STATUS_CHANGE.name,
            raw_body=json.dumps({'data': {}}),
        )
        self.logistics_center_message_non_existing_inbound = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'CONSIGNEE': 'NKS',
                            'ORDERID': _platform_id_to_pap_id(0),
                            'SOURCECOMPANY': 'company',
                            'STATUS': 'RECEIVED',
                            'PRIORITYPOID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_non_existing_inbound.created_at = datetime(
            year=2024, month=8, day=1, hour=12
        )
        self.logistics_center_message_non_existing_inbound.save()
        self.logistics_center_message_inbound_partially_completed_status_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'CONSIGNEE': 'NKS',
                            'ORDERID': _platform_id_to_pap_id(self.purchase_order_1.pk),
                            'SOURCECOMPANY': 'company',
                            'STATUS': 'PARTIALLY COMPLETED',
                            'PRIORITYPOID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_inbound_partially_completed_status_update.created_at = datetime(  # noqa: E501
            year=2024, month=8, day=1, hour=12
        )
        self.logistics_center_message_inbound_partially_completed_status_update.save()
        self.logistics_center_message_inbound_completed_status_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'CONSIGNEE': 'NKS',
                            'ORDERID': _platform_id_to_pap_id(self.purchase_order_1.pk),
                            'SOURCECOMPANY': 'company',
                            'STATUS': 'COMPLETED',
                            'PRIORITYPOID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_inbound_completed_status_update.created_at = (
            datetime(year=2024, month=8, day=2, hour=12)
        )
        self.logistics_center_message_inbound_completed_status_update.save()
        self.logistics_center_message_inbound_received_late_status_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'CONSIGNEE': 'NKS',
                            'ORDERID': _platform_id_to_pap_id(self.purchase_order_1.pk),
                            'SOURCECOMPANY': 'company',
                            'STATUS': 'RECEIVED',
                            'PRIORITYPOID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_inbound_received_late_status_update.created_at = (
            datetime(year=2024, month=8, day=1, hour=6)
        )
        self.logistics_center_message_inbound_received_late_status_update.save()

    def test_message_not_found(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async((123,))
        self.assertTrue(
            isinstance(ex_retry.exception.exc, LogisticsCenterMessage.DoesNotExist)
        )

    def test_invalid_message(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_1.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_2.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

    def test_inbound_id_not_found(self):
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_non_existing_inbound.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, PurchaseOrder.DoesNotExist))

        # no inbound status records should have been created
        self.assertEquals(len(LogisticsCenterInboundStatus.objects.all()), 0)

        # logistics center status should not have been set
        self.assertEquals(PurchaseOrder.objects.first().logistics_center_status, None)

    def test_inbound_successful_status_updates(self):
        process_logistics_center_message.apply_async(
            (
                self.logistics_center_message_inbound_partially_completed_status_update.pk,
            )
        )

        # an inbound status record was created
        self.assertEquals(len(LogisticsCenterInboundStatus.objects.all()), 1)
        inbound_status = LogisticsCenterInboundStatus.objects.first()
        self.assertEquals(inbound_status.status, 'PARTIALLY COMPLETED')
        self.assertEquals(
            inbound_status.status_date_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2024-08-01 09:00:00',
        )

        # logistics center status should have been set
        self.purchase_order_1.refresh_from_db()
        self.assertEquals(
            self.purchase_order_1.logistics_center_status, 'PARTIALLY COMPLETED'
        )

        process_logistics_center_message.apply_async(
            (self.logistics_center_message_inbound_completed_status_update.pk,)
        )

        # another inbound status record was created
        self.assertEquals(len(LogisticsCenterInboundStatus.objects.all()), 2)
        inbound_status = LogisticsCenterInboundStatus.objects.all()[1]
        self.assertEquals(inbound_status.status, 'COMPLETED')
        self.assertEquals(
            inbound_status.status_date_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2024-08-02 09:00:00',
        )

        # logistics center status should have been updated since the received
        # status date is newer than the previous one
        self.purchase_order_1.refresh_from_db()
        self.assertEquals(self.purchase_order_1.logistics_center_status, 'COMPLETED')

        process_logistics_center_message.apply_async(
            (self.logistics_center_message_inbound_received_late_status_update.pk,)
        )

        # another inbound status record was created
        self.assertEquals(len(LogisticsCenterInboundStatus.objects.all()), 3)
        inbound_status = LogisticsCenterInboundStatus.objects.all()[2]
        self.assertEquals(inbound_status.status, 'RECEIVED')
        self.assertEquals(
            inbound_status.status_date_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2024-08-01 03:00:00',
        )

        # logistics center status should not have been updated since the
        # received status date is older than the previous one
        self.purchase_order_1.refresh_from_db()
        self.assertEquals(self.purchase_order_1.logistics_center_status, 'COMPLETED')

        process_logistics_center_message.apply_async(
            (
                self.logistics_center_message_inbound_partially_completed_status_update.pk,
            )
        )

        # receiving a status update again should not create another inbound
        # status record
        self.assertEquals(len(LogisticsCenterInboundStatus.objects.all()), 3)


class ProcessLogisticsCenterInboundReceiptMessageTestCase(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(
            name='supplier name',
        )
        self.brand = Brand.objects.create(
            name='brand name',
        )
        self.product_1 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 1 name',
            sku='1',
            cost_price=50,
            sale_price=60,
        )
        self.product_2 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 2 name',
            sku='2',
            cost_price=70,
            sale_price=80,
        )
        self.purchase_order_1 = PurchaseOrder.objects.create(
            supplier=self.supplier,
            logistics_center=LogisticsCenterEnum.PICK_AND_PACK.name,
            logistics_center_id='1000',
        )
        self.purchase_order_product_1 = PurchaseOrderProduct.objects.create(
            product_id=self.product_1,
            purchase_order=self.purchase_order_1,
            quantity_ordered=1,
            quantity_sent_to_logistics_center=0,
        )
        self.purchase_order_2 = PurchaseOrder.objects.create(
            supplier=self.supplier,
            logistics_center=LogisticsCenterEnum.PICK_AND_PACK.name,
            logistics_center_id='2000',
        )
        self.purchase_order_product_2 = PurchaseOrderProduct.objects.create(
            product_id=self.product_1,
            purchase_order=self.purchase_order_2,
            quantity_ordered=2,
            quantity_sent_to_logistics_center=0,
        )
        self.purchase_order_product_3 = PurchaseOrderProduct.objects.create(
            product_id=self.product_2,
            purchase_order=self.purchase_order_2,
            quantity_ordered=3,
            quantity_sent_to_logistics_center=0,
        )
        self.logistics_center_message_invalid_1 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
            raw_body='{}',
        )
        self.logistics_center_message_invalid_2 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
            raw_body=json.dumps({'data': {}}),
        )
        self.logistics_center_message_no_lines = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
            raw_body=json.dumps(
                {
                    'data': {
                        'RECEIPT': 'CODE1',
                        'STARTRECEIPTDATE': '8/1/2024 12:00:00 +0200',
                        'CLOSERECEIPTDATE': '',
                        'PRIORITYPOID': '1000',
                        'STATUS': 'unknown',
                        'LINES': {'LINE': []},
                    }
                }
            ),
        )
        self.logistics_center_message_non_existing_order = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'RECEIPT': 'CODE2',
                            'STARTRECEIPTDATE': '8/1/2024 12:00:00 +0200',
                            'PRIORITYPOID': '1001',
                            'ORDERID': _platform_id_to_pap_id(0),
                            'STATUS': 'unknown',
                            'LINES': {
                                'LINE': [
                                    {
                                        'RECEIPTLINE': 1,
                                        'SKU': '0',
                                        'QTYRECEIVED': 1,
                                        'QTYORIGINAL': 1,
                                    },
                                ],
                            },
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_single_line = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'RECEIPT': 'CODE3',
                            'STARTRECEIPTDATE': '8/1/2024 12:00:00 +0200',
                            'PRIORITYPOID': '1000',
                            'ORDERID': _platform_id_to_pap_id(self.purchase_order_1.pk),
                            'STATUS': 'unknown',
                            'LINES': {
                                'LINE': [
                                    {
                                        'RECEIPTLINE': 1,
                                        'SKU': self.product_1.sku,
                                        'QTYRECEIVED': 1,
                                        'QTYORIGINAL': 1,
                                    },
                                ],
                            },
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_multi_line = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'RECEIPT': 'CODE4',
                            'STARTRECEIPTDATE': '8/1/2024 12:00:00 +0200',
                            'PRIORITYPOID': '2000',
                            'ORDERID': _platform_id_to_pap_id(self.purchase_order_2.pk),
                            'STATUS': 'unknown',
                            'LINES': {
                                'LINE': [
                                    {
                                        'RECEIPTLINE': 1,
                                        'SKU': self.product_1.sku,
                                        'QTYRECEIVED': 3,
                                        'QTYORIGINAL': 33,
                                    },
                                    {
                                        'RECEIPTLINE': 2,
                                        'SKU': self.product_2.sku,
                                        'QTYRECEIVED': 15,
                                        'QTYORIGINAL': 165,
                                    },
                                ],
                            },
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_multi_line_quantity_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'RECEIPT': 'CODE4',
                            'STARTRECEIPTDATE': '8/2/2024 16:00:00 +0200',
                            'PRIORITYPOID': '2000',
                            'ORDERID': _platform_id_to_pap_id(self.purchase_order_2.pk),
                            'STATUS': 'unknown',
                            'LINES': {
                                'LINE': [
                                    {
                                        'RECEIPTLINE': 1,
                                        'SKU': self.product_1.sku,
                                        'QTYRECEIVED': 30,
                                        'QTYORIGINAL': 30,
                                    },
                                    {
                                        'RECEIPTLINE': 2,
                                        'SKU': self.product_2.sku,
                                        'QTYRECEIVED': 150,
                                        'QTYORIGINAL': 150,
                                    },
                                ],
                            },
                        }
                    }
                ),
            )
        )

    def test_message_not_found(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async((123,))
        self.assertTrue(
            isinstance(ex_retry.exception.exc, LogisticsCenterMessage.DoesNotExist)
        )

    def test_invalid_message(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_1.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_2.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

    def test_no_receipt_lines(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_no_lines.pk,)
        )

        # a receipt was created
        self.assertEquals(len(LogisticsCenterInboundReceipt.objects.all()), 1)
        self.assertEquals(
            LogisticsCenterInboundReceipt.objects.first().receipt_code, 'CODE1'
        )

        # no lines were created since none were received
        self.assertEquals(len(LogisticsCenterInboundReceiptLine.objects.all()), 0)

    def test_order_id_not_found(self):
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_non_existing_order.pk,)
            )
        self.assertTrue(
            isinstance(ex_retry.exception.exc, PurchaseOrderProduct.DoesNotExist)
        )

        # a receipt was still created
        self.assertEquals(len(LogisticsCenterInboundReceipt.objects.all()), 1)
        self.assertEquals(
            LogisticsCenterInboundReceipt.objects.first().receipt_code, 'CODE2'
        )

        # no receipt lines should have been created due to the error
        self.assertEquals(len(LogisticsCenterInboundReceiptLine.objects.all()), 0)

    def test_single_line_receipt(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_single_line.pk,)
        )

        # a receipt was created
        self.assertEquals(len(LogisticsCenterInboundReceipt.objects.all()), 1)
        receipt = LogisticsCenterInboundReceipt.objects.first()
        self.assertEquals(receipt.receipt_code, 'CODE3')

        # a receipt line was also created
        self.assertEquals(len(LogisticsCenterInboundReceiptLine.objects.all()), 1)
        receipt_line = LogisticsCenterInboundReceiptLine.objects.first()
        self.assertEquals(receipt_line.receipt, receipt)
        self.assertEquals(receipt_line.receipt_line, 1)
        self.assertEquals(
            receipt_line.purchase_order_product, self.purchase_order_product_1
        )
        self.assertEquals(receipt_line.quantity_received, 1)
        self.assertEquals(
            receipt_line.logistics_center_message,
            self.logistics_center_message_single_line,
        )

    def test_multi_line_receipt(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_multi_line.pk,)
        )

        # a receipt was created
        self.assertEquals(len(LogisticsCenterInboundReceipt.objects.all()), 1)
        receipt = LogisticsCenterInboundReceipt.objects.first()
        self.assertEquals(receipt.receipt_code, 'CODE4')

        # two receipt lines were also created
        self.assertEquals(len(LogisticsCenterInboundReceiptLine.objects.all()), 2)
        receipt_line_1 = LogisticsCenterInboundReceiptLine.objects.order_by(
            'receipt_line'
        ).all()[0]
        self.assertEquals(receipt_line_1.receipt, receipt)
        self.assertEquals(receipt_line_1.receipt_line, 1)
        self.assertEquals(
            receipt_line_1.purchase_order_product, self.purchase_order_product_2
        )
        self.assertEquals(receipt_line_1.quantity_received, 3)
        self.assertEquals(
            receipt_line_1.logistics_center_message,
            self.logistics_center_message_multi_line,
        )
        receipt_line_2 = LogisticsCenterInboundReceiptLine.objects.order_by(
            'receipt_line'
        ).all()[1]
        self.assertEquals(receipt_line_2.receipt, receipt)
        self.assertEquals(receipt_line_2.receipt_line, 2)
        self.assertEquals(
            receipt_line_2.purchase_order_product, self.purchase_order_product_3
        )
        self.assertEquals(receipt_line_2.quantity_received, 15)
        self.assertEquals(
            receipt_line_2.logistics_center_message,
            self.logistics_center_message_multi_line,
        )

    def test_multi_line_receipt_with_update(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_multi_line.pk,)
        )

        # a receipt was created
        self.assertEquals(len(LogisticsCenterInboundReceipt.objects.all()), 1)
        receipt = LogisticsCenterInboundReceipt.objects.first()
        self.assertEquals(receipt.receipt_code, 'CODE4')
        self.assertEquals(
            receipt.receipt_start_date,
            datetime(year=2024, month=8, day=1, hour=10, minute=0, tzinfo=timezone.utc),
        )
        self.assertEquals(receipt.receipt_close_date, None)

        # two receipt lines were also created
        self.assertEquals(len(LogisticsCenterInboundReceiptLine.objects.all()), 2)
        receipt_line_1 = LogisticsCenterInboundReceiptLine.objects.order_by(
            'receipt_line'
        ).all()[0]
        self.assertEquals(receipt_line_1.receipt, receipt)
        self.assertEquals(receipt_line_1.receipt_line, 1)
        self.assertEquals(
            receipt_line_1.purchase_order_product, self.purchase_order_product_2
        )
        self.assertEquals(receipt_line_1.quantity_received, 3)
        self.assertEquals(
            receipt_line_1.logistics_center_message,
            self.logistics_center_message_multi_line,
        )
        receipt_line_2 = LogisticsCenterInboundReceiptLine.objects.order_by(
            'receipt_line'
        ).all()[1]
        self.assertEquals(receipt_line_2.receipt, receipt)
        self.assertEquals(receipt_line_2.receipt_line, 2)
        self.assertEquals(
            receipt_line_2.purchase_order_product, self.purchase_order_product_3
        )
        self.assertEquals(receipt_line_2.quantity_received, 15)
        self.assertEquals(
            receipt_line_2.logistics_center_message,
            self.logistics_center_message_multi_line,
        )

        # process message for the same receipt with quantity updates (this
        # should not occur in real life, but can be handled nontheless)
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_multi_line_quantity_update.pk,)
        )

        # another receipt was not created
        self.assertEquals(len(LogisticsCenterInboundReceipt.objects.all()), 1)
        receipt = LogisticsCenterInboundReceipt.objects.first()
        self.assertEquals(receipt.receipt_code, 'CODE4')
        self.assertEquals(
            receipt.receipt_start_date,
            datetime(year=2024, month=8, day=2, hour=14, minute=0, tzinfo=timezone.utc),
        )
        self.assertEquals(receipt.receipt_close_date, None)

        # the two receipt lines were updated
        self.assertEquals(len(LogisticsCenterInboundReceiptLine.objects.all()), 2)
        receipt_line_1 = LogisticsCenterInboundReceiptLine.objects.order_by(
            'receipt_line'
        ).all()[0]
        self.assertEquals(receipt_line_1.receipt, receipt)
        self.assertEquals(receipt_line_1.receipt_line, 1)
        self.assertEquals(
            receipt_line_1.purchase_order_product, self.purchase_order_product_2
        )
        self.assertEquals(receipt_line_1.quantity_received, 30)
        self.assertEquals(
            receipt_line_1.logistics_center_message,
            self.logistics_center_message_multi_line_quantity_update,
        )
        receipt_line_2 = LogisticsCenterInboundReceiptLine.objects.order_by(
            'receipt_line'
        ).all()[1]
        self.assertEquals(receipt_line_2.receipt, receipt)
        self.assertEquals(receipt_line_2.receipt_line, 2)
        self.assertEquals(
            receipt_line_2.purchase_order_product, self.purchase_order_product_3
        )
        self.assertEquals(receipt_line_2.quantity_received, 150)
        self.assertEquals(
            receipt_line_2.logistics_center_message,
            self.logistics_center_message_multi_line_quantity_update,
        )


class ProcessLogisticsCenterOrderStatusChangeMessageTestCase(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(
            name='supplier name',
        )
        self.brand = Brand.objects.create(
            name='brand name',
        )
        self.product_1 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 1 name',
            sku='1',
            cost_price=50,
            sale_price=60,
        )
        self.product_2 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 2 name',
            sku='2',
            cost_price=70,
            sale_price=80,
        )

        # create the campaign infrastructure for the orders we need
        organization = Organization.objects.create(
            name='Test organization',
            manager_full_name='Test manager',
            manager_phone_number='0500000009',
            manager_email='manager@test.test',
        )
        campaign = Campaign.objects.create(
            name='Test campaign',
            organization=organization,
            status=Campaign.CampaignStatusEnum.ACTIVE.name,
            start_date_time=datetime.now(),
            end_date_time=datetime.now(),
        )
        employee_group = EmployeeGroup.objects.create(
            name='Test employee group 1',
            organization=organization,
            delivery_city='Office1',
            delivery_street='Office street 1',
            delivery_street_number='1',
            delivery_apartment_number='2',
            delivery_location=DeliveryLocationEnum.ToHome.name,
        )
        employee_group_campaign = EmployeeGroupCampaign.objects.create(
            employee_group=employee_group, campaign=campaign, budget_per_employee=100
        )
        employee = Employee.objects.create(
            employee_group=employee_group,
            first_name='Test',
            last_name='Employee 1',
            email='test1@test.test',
        )
        employee_group_campaign_product = EmployeeGroupCampaignProduct.objects.create(
            employee_group_campaign_id=employee_group_campaign,
            product_id=self.product_1,
        )

        # the order we need for testing outbound
        self.order = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=employee
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 1',
            phone_number='0500000000',
            additional_phone_number='050000001',
            delivery_city='City1',
            delivery_street='Main1',
            delivery_street_number='1',
            delivery_apartment_number='1',
            delivery_additional_details='Additional 1',
            logistics_center=LogisticsCenterEnum.PICK_AND_PACK.name,
            logistics_center_id='1000',
        )
        OrderProduct.objects.create(
            order_id=self.order,
            product_id=employee_group_campaign_product,
            quantity=1,
        )

        self.logistics_center_message_invalid_1 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
            raw_body='{}',
        )
        self.logistics_center_message_invalid_2 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
            raw_body=json.dumps({'data': {}}),
        )
        self.logistics_center_message_non_existing_order = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'CONSIGNEE': 'NKS',
                            'ORDERID': 'unknown',
                            'ORDERTYPE': 'CUSTOMER',
                            'STATUS': 'RECEIVED',
                            'PRIORITY_ORDER_ID': '1001',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_non_existing_order.created_at = datetime(
            year=2024, month=8, day=1, hour=12
        )
        self.logistics_center_message_non_existing_order.save()
        self.logistics_center_message_order_picked_status_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'CONSIGNEE': 'NKS',
                            'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                            'ORDERTYPE': 'CUSTOMER',
                            'STATUS': 'PICKED',
                            'PRIORITY_ORDER_ID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_order_picked_status_update.created_at = datetime(
            year=2024, month=8, day=1, hour=12
        )
        self.logistics_center_message_order_picked_status_update.save()
        self.logistics_center_message_order_transported_status_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'CONSIGNEE': 'NKS',
                            'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                            'ORDERTYPE': 'CUSTOMER',
                            'STATUS': 'TRANSPORTED',
                            'PRIORITY_ORDER_ID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_order_transported_status_update.created_at = (
            datetime(year=2024, month=8, day=2, hour=12)
        )
        self.logistics_center_message_order_transported_status_update.save()
        self.logistics_center_message_order_received_late_status_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'CONSIGNEE': 'NKS',
                            'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                            'ORDERTYPE': 'CUSTOMER',
                            'STATUS': 'RECEIVED',
                            'PRIORITY_ORDER_ID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_order_received_late_status_update.created_at = (
            datetime(year=2024, month=8, day=1, hour=6)
        )
        self.logistics_center_message_order_received_late_status_update.save()

    def test_message_not_found(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async((123,))
        self.assertTrue(
            isinstance(ex_retry.exception.exc, LogisticsCenterMessage.DoesNotExist)
        )

    def test_invalid_message(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_1.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_2.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

    def test_priority_order_id_not_found(self):
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_non_existing_order.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, Order.DoesNotExist))

        # no order status records should have been created
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 0)

        # logistics center status should not have been set
        self.assertEquals(Order.objects.first().logistics_center_status, None)

    def test_order_successful_status_updates(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_order_picked_status_update.pk,)
        )

        # an order status record was created
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 1)
        order_status = LogisticsCenterOrderStatus.objects.first()
        self.assertEquals(order_status.status, 'PICKED')
        self.assertEquals(
            order_status.status_date_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2024-08-01 09:00:00',
        )

        # logistics center status should have been set
        self.order.refresh_from_db()
        self.assertEquals(self.order.logistics_center_status, 'PICKED')

        process_logistics_center_message.apply_async(
            (self.logistics_center_message_order_transported_status_update.pk,)
        )

        # another order status record was created
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 2)
        order_status = LogisticsCenterOrderStatus.objects.all()[1]
        self.assertEquals(order_status.status, 'TRANSPORTED')
        self.assertEquals(
            order_status.status_date_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2024-08-02 09:00:00',
        )

        # logistics center status should have been updated since the received
        # status date is newer than the previous one
        self.order.refresh_from_db()
        self.assertEquals(self.order.logistics_center_status, 'TRANSPORTED')

        process_logistics_center_message.apply_async(
            (self.logistics_center_message_order_received_late_status_update.pk,)
        )

        # another order status record was created
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 3)
        order_status = LogisticsCenterOrderStatus.objects.all()[2]
        self.assertEquals(order_status.status, 'RECEIVED')
        self.assertEquals(
            order_status.status_date_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2024-08-01 03:00:00',
        )

        # logistics center status should not have been updated since the
        # received status date is older than the previous one
        self.order.refresh_from_db()
        self.assertEquals(self.order.logistics_center_status, 'TRANSPORTED')

        process_logistics_center_message.apply_async(
            (self.logistics_center_message_order_transported_status_update.pk,)
        )

        # receiving a status update again should not create another order
        # status record
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 3)


class ProcessLogisticsCenterShipOrderMessageTestCase(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(
            name='supplier name',
        )
        self.brand = Brand.objects.create(
            name='brand name',
        )
        self.product_1 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 1 name',
            sku='1',
            cost_price=50,
            sale_price=60,
        )
        self.product_2 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 2 name',
            sku='2',
            cost_price=70,
            sale_price=80,
        )

        # create the campaign infrastructure for the orders we need
        organization = Organization.objects.create(
            name='Test organization',
            manager_full_name='Test manager',
            manager_phone_number='0500000009',
            manager_email='manager@test.test',
        )
        campaign = Campaign.objects.create(
            name='Test campaign',
            organization=organization,
            status=Campaign.CampaignStatusEnum.ACTIVE.name,
            start_date_time=datetime.now(),
            end_date_time=datetime.now(),
        )
        employee_group = EmployeeGroup.objects.create(
            name='Test employee group 1',
            organization=organization,
            delivery_city='Office1',
            delivery_street='Office street 1',
            delivery_street_number='1',
            delivery_apartment_number='2',
            delivery_location=DeliveryLocationEnum.ToHome.name,
        )
        employee_group_campaign = EmployeeGroupCampaign.objects.create(
            employee_group=employee_group, campaign=campaign, budget_per_employee=100
        )
        employee = Employee.objects.create(
            employee_group=employee_group,
            first_name='Test',
            last_name='Employee 1',
            email='test1@test.test',
        )
        employee_group_campaign_product = EmployeeGroupCampaignProduct.objects.create(
            employee_group_campaign_id=employee_group_campaign,
            product_id=self.product_1,
        )

        # the order we need for testing outbound
        self.order = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=campaign, employee=employee
            ),
            order_date_time=datetime.now(),
            cost_from_budget=100,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
            full_name='Test name 1',
            phone_number='0500000000',
            additional_phone_number='050000001',
            delivery_city='City1',
            delivery_street='Main1',
            delivery_street_number='1',
            delivery_apartment_number='1',
            delivery_additional_details='Additional 1',
            logistics_center=LogisticsCenterEnum.PICK_AND_PACK.name,
            logistics_center_id='1000',
        )
        OrderProduct.objects.create(
            order_id=self.order,
            product_id=employee_group_campaign_product,
            quantity=1,
        )

        self.logistics_center_message_invalid_1 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
            raw_body='{}',
        )
        self.logistics_center_message_invalid_2 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
            raw_body=json.dumps({'data': {}}),
        )
        self.logistics_center_message_non_existing_order = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'ORDERID': 'unknown',
                            'SHIPPING_STATUS': 'PICKED',
                            'SHIPNU': 'abc123',
                            'PRIORITY_ORDER_ID': '1001',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_ship_order = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                            'SHIPPING_STATUS': 'SHIPPED',
                            'SHIPNU': 'abc123',
                            'PRIORITY_ORDER_ID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_ship_order.created_at = datetime(
            year=2024, month=8, day=1, hour=12
        )
        self.logistics_center_message_ship_order.save()
        self.logistics_center_message_ship_order_late = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                            'SHIPPING_STATUS': 'SHIPPEDAGAIN',
                            'SHIPNU': 'abc123',
                            'PRIORITY_ORDER_ID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_ship_order_late.created_at = datetime(
            year=2024, month=8, day=1, hour=6
        )
        self.logistics_center_message_ship_order_late.save()
        self.logistics_center_message_ship_order_no_status = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
                raw_body=json.dumps(
                    {
                        'data': {
                            'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                            'SHIPNU': 'abc123',
                            'PRIORITY_ORDER_ID': '1000',
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_ship_order_no_status.created_at = datetime(
            year=2024, month=8, day=1, hour=14
        )
        self.logistics_center_message_ship_order_no_status.save()

    def test_message_not_found(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async((123,))
        self.assertTrue(
            isinstance(ex_retry.exception.exc, LogisticsCenterMessage.DoesNotExist)
        )

    def test_invalid_message(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_1.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_2.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

    def test_order_id_not_found(self):
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_non_existing_order.pk,),
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, Order.DoesNotExist))

        # no order status records should have been created
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 0)

        # logistics center status should not have been set
        self.assertEquals(Order.objects.first().logistics_center_status, None)

    def test_order_successful_status_updates(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_ship_order.pk,)
        )

        # an order status record was created
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 1)
        order_status = LogisticsCenterOrderStatus.objects.first()
        self.assertEquals(order_status.status, 'SHIPPED')
        self.assertEquals(
            order_status.status_date_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2024-08-01 09:00:00',
        )

        # logistics center status should have been set
        self.order.refresh_from_db()
        self.assertEquals(self.order.logistics_center_status, 'SHIPPED')
        self.assertEquals(self.order.logistics_center_shipping_number, 'abc123')

        process_logistics_center_message.apply_async(
            (self.logistics_center_message_ship_order_late.pk,)
        )

        # another order status record was created
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 2)
        order_status = LogisticsCenterOrderStatus.objects.all()[1]
        self.assertEquals(order_status.status, 'SHIPPEDAGAIN')
        self.assertEquals(
            order_status.status_date_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2024-08-01 03:00:00',
        )

        # logistics center status should not have been updated since the
        # received status date is older than the previous one
        self.order.refresh_from_db()
        self.assertEquals(self.order.logistics_center_status, 'SHIPPED')
        self.assertEquals(self.order.logistics_center_shipping_number, 'abc123')

        process_logistics_center_message.apply_async(
            (self.logistics_center_message_ship_order.pk,)
        )

        # receiving a ship order again should not create another order
        # status record
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 2)

    def test_order_successful_no_status(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_ship_order_no_status.pk,)
        )

        # no order status record was created
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 0)

        # there should be no logistics center status and there should be a
        # shipping number
        self.order.refresh_from_db()
        self.assertEquals(self.order.logistics_center_status, None)
        self.assertEquals(self.order.logistics_center_shipping_number, 'abc123')

        process_logistics_center_message.apply_async(
            (self.logistics_center_message_ship_order.pk,)
        )

        # now an order status record was created
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 1)
        order_status = LogisticsCenterOrderStatus.objects.all()[0]
        self.assertEquals(order_status.status, 'SHIPPED')
        self.assertEquals(
            order_status.status_date_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2024-08-01 09:00:00',
        )

        # logistics center status should have been updated even with the latest
        # message being earlier than the one with no status
        self.order.refresh_from_db()
        self.assertEquals(self.order.logistics_center_status, 'SHIPPED')
        self.assertEquals(self.order.logistics_center_shipping_number, 'abc123')


class ProcessLogisticsCenterSnapshotTestCase(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(
            name='supplier name',
        )
        self.brand = Brand.objects.create(
            name='brand name',
        )
        self.product_1 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 1 name',
            sku='1',
            cost_price=50,
            sale_price=60,
        )
        self.product_2 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 2 name',
            sku='2',
            cost_price=70,
            sale_price=80,
        )

        self.logistics_center_message_invalid_1 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.SNAPSHOT.name,
            raw_body='{}',
        )
        self.logistics_center_message_invalid_2 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.SNAPSHOT.name,
            raw_body=json.dumps({'data': {}}),
        )
        self.logistics_center_message_no_lines = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.SNAPSHOT.name,
            raw_body=json.dumps(
                {
                    'type': 'snapshot',
                    'data': {'snapshotDateTime': '02/03/2025 10:00:00', 'lines': []},
                }
            ),
        )
        self.logistics_center_message_single_line = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.SNAPSHOT.name,
                raw_body=json.dumps(
                    {
                        'type': 'snapshot',
                        'data': {
                            'snapshotDateTime': '02/03/2025 10:00:00',
                            'lines': [{'sku': '1', 'quantity': 1}],
                        },
                    }
                ),
            )
        )
        self.logistics_center_message_multi_line = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.PICK_AND_PACK.name,
                message_type=LogisticsCenterMessageTypeEnum.SNAPSHOT.name,
                raw_body=json.dumps(
                    {
                        'type': 'snapshot',
                        'data': {
                            'snapshotDateTime': '02/03/2025 10:00:00',
                            'lines': [
                                {'sku': '1', 'quantity': 2},
                                {'sku': '2', 'quantity': 3},
                                {'sku': '3', 'quantity': 15},
                            ],
                        },
                    }
                ),
            )
        )
        self.logistics_center_message_updates_1 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.SNAPSHOT.name,
            raw_body=json.dumps(
                {
                    'type': 'snapshot',
                    'data': {
                        'snapshotDateTime': '02/03/2025 10:00:00',
                        'lines': [
                            {'sku': '1', 'quantity': 4},
                            {'sku': '1', 'quantity': 2},
                            {'sku': '2', 'quantity': 5},
                            {'sku': '2', 'quantity': 9},
                        ],
                    },
                }
            ),
        )
        self.logistics_center_message_updates_2 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.SNAPSHOT.name,
            raw_body=json.dumps(
                {
                    'type': 'snapshot',
                    'data': {
                        'snapshotDateTime': '02/03/2025 11:00:00',
                        'lines': [{'sku': '2', 'quantity': 6}],
                    },
                }
            ),
        )
        self.logistics_center_message_updates_3 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.PICK_AND_PACK.name,
            message_type=LogisticsCenterMessageTypeEnum.SNAPSHOT.name,
            raw_body=json.dumps(
                {
                    'type': 'snapshot',
                    'data': {
                        'snapshotDateTime': '02/03/2025 09:00:00',
                        'lines': [
                            {'sku': '1', 'quantity': 7},
                            {'sku': '2', 'quantity': 8},
                        ],
                    },
                }
            ),
        )

    def test_message_not_found(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async((123,))
        self.assertTrue(
            isinstance(ex_retry.exception.exc, LogisticsCenterMessage.DoesNotExist)
        )

    def test_invalid_message(self):
        # the task should raise errors if any occur that cannot be handled so
        # we know it is failing
        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_1.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

        with self.assertRaises(Retry) as ex_retry:
            process_logistics_center_message.apply_async(
                (self.logistics_center_message_invalid_2.pk,)
            )
        self.assertTrue(isinstance(ex_retry.exception.exc, KeyError))

    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_no_snapshot_lines(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_no_lines.pk,)
        )

        # a receipt was created
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 1)
        self.assertEquals(
            LogisticsCenterStockSnapshot.objects.first().snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=10, minute=0, tzinfo=timezone.utc),
        )

        # no lines were created since none were received
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 0)

    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_single_line_receipt(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_single_line.pk,)
        )

        # one stock snapshot was created
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 1)
        stock_1 = LogisticsCenterStockSnapshot.objects.first()
        self.assertEquals(
            stock_1.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=10, minute=0, tzinfo=timezone.utc),
        )

        # one stock snapshot line was created
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 1)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.first()
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 1)

        # the correct product was linked to the stock snapshot line
        self.product_1.refresh_from_db()
        self.product_2.refresh_from_db()
        self.assertEquals(self.product_1.logistics_snapshot_stock_line, stock_line_1)
        self.assertEquals(self.product_2.logistics_snapshot_stock_line, None)

    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_multi_line_receipt(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_multi_line.pk,)
        )

        # one stock snapshot was created
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 1)
        stock_1 = LogisticsCenterStockSnapshot.objects.first()
        self.assertEquals(
            stock_1.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=10, minute=0, tzinfo=timezone.utc),
        )

        # three stock snapshot lines were created
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 3)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.all()[0]
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 2)
        stock_line_2 = LogisticsCenterStockSnapshotLine.objects.all()[1]
        self.assertEquals(stock_line_2.stock_snapshot, stock_1)
        self.assertEquals(stock_line_2.sku, '2')
        self.assertEquals(stock_line_2.quantity, 3)
        stock_line_3 = LogisticsCenterStockSnapshotLine.objects.all()[2]
        self.assertEquals(stock_line_3.stock_snapshot, stock_1)
        self.assertEquals(stock_line_3.sku, '3')
        self.assertEquals(stock_line_3.quantity, 15)

        # the correct products were linked to the stock snapshot line
        self.product_1.refresh_from_db()
        self.product_2.refresh_from_db()
        self.assertEquals(self.product_1.logistics_snapshot_stock_line, stock_line_1)
        self.assertEquals(self.product_2.logistics_snapshot_stock_line, stock_line_2)

    @override_settings(PAP_MESSAGE_TIMEZONE_NAME='UTC')
    def test_multi_line_receipt_with_update(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_updates_1.pk,)
        )

        # one stock snapshot was created
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 1)
        stock_1 = LogisticsCenterStockSnapshot.objects.first()
        self.assertEquals(
            stock_1.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=10, minute=0, tzinfo=timezone.utc),
        )

        # two stock snapshot lines were created
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 2)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.all()[0]
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 6)
        stock_line_2 = LogisticsCenterStockSnapshotLine.objects.all()[1]
        self.assertEquals(stock_line_2.stock_snapshot, stock_1)
        self.assertEquals(stock_line_2.sku, '2')
        self.assertEquals(stock_line_2.quantity, 14)

        # the correct products were linked to the stock snapshot line
        self.product_1.refresh_from_db()
        self.product_2.refresh_from_db()
        self.assertEquals(self.product_1.logistics_snapshot_stock_line, stock_line_1)
        self.assertEquals(self.product_2.logistics_snapshot_stock_line, stock_line_2)

        # process message for another snapshot
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_updates_2.pk,)
        )

        # two stock snapshot should now exist
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 2)
        stock_1 = LogisticsCenterStockSnapshot.objects.all()[0]
        self.assertEquals(
            stock_1.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=10, minute=0, tzinfo=timezone.utc),
        )
        stock_2 = LogisticsCenterStockSnapshot.objects.all()[1]
        self.assertEquals(
            stock_2.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=11, minute=0, tzinfo=timezone.utc),
        )

        # three stock snapshot lines should now exist
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 3)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.all()[0]
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 6)
        stock_line_2 = LogisticsCenterStockSnapshotLine.objects.all()[1]
        self.assertEquals(stock_line_2.stock_snapshot, stock_1)
        self.assertEquals(stock_line_2.sku, '2')
        self.assertEquals(stock_line_2.quantity, 14)
        stock_line_3 = LogisticsCenterStockSnapshotLine.objects.all()[2]
        self.assertEquals(stock_line_3.stock_snapshot, stock_2)
        self.assertEquals(stock_line_3.sku, '2')
        self.assertEquals(stock_line_3.quantity, 6)

        # the correct products were linked to the stock snapshot line
        self.product_1.refresh_from_db()
        self.product_2.refresh_from_db()
        self.assertEquals(self.product_1.logistics_snapshot_stock_line, None)
        self.assertEquals(self.product_2.logistics_snapshot_stock_line, stock_line_3)

        # process the third snapshot - which has an earlier date time than the
        # previously-processed snapshots
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_updates_3.pk,)
        )

        # three stock snapshot should now exist
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 3)
        stock_1 = LogisticsCenterStockSnapshot.objects.all()[0]
        self.assertEquals(
            stock_1.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=10, minute=0, tzinfo=timezone.utc),
        )
        stock_2 = LogisticsCenterStockSnapshot.objects.all()[1]
        self.assertEquals(
            stock_2.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=11, minute=0, tzinfo=timezone.utc),
        )
        stock_3 = LogisticsCenterStockSnapshot.objects.all()[2]
        self.assertEquals(
            stock_3.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=9, minute=0, tzinfo=timezone.utc),
        )

        # five stock snapshot lines should now exist
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 5)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.all()[0]
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 6)
        stock_line_2 = LogisticsCenterStockSnapshotLine.objects.all()[1]
        self.assertEquals(stock_line_2.stock_snapshot, stock_1)
        self.assertEquals(stock_line_2.sku, '2')
        self.assertEquals(stock_line_2.quantity, 14)
        stock_line_3 = LogisticsCenterStockSnapshotLine.objects.all()[2]
        self.assertEquals(stock_line_3.stock_snapshot, stock_2)
        self.assertEquals(stock_line_3.sku, '2')
        self.assertEquals(stock_line_3.quantity, 6)
        stock_line_4 = LogisticsCenterStockSnapshotLine.objects.all()[3]
        self.assertEquals(stock_line_4.stock_snapshot, stock_3)
        self.assertEquals(stock_line_4.sku, '1')
        self.assertEquals(stock_line_4.quantity, 7)
        stock_line_5 = LogisticsCenterStockSnapshotLine.objects.all()[4]
        self.assertEquals(stock_line_5.stock_snapshot, stock_3)
        self.assertEquals(stock_line_5.sku, '2')
        self.assertEquals(stock_line_5.quantity, 8)

        # product stock snapshot lines were not updated since the last
        # processed snapshot is an earlier-dated one
        self.product_1.refresh_from_db()
        self.product_2.refresh_from_db()
        self.assertEquals(self.product_1.logistics_snapshot_stock_line, None)
        self.assertEquals(self.product_2.logistics_snapshot_stock_line, stock_line_3)

        # process the first snapshot - data should be updated and new stock
        # records should not be created
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_updates_1.pk,)
        )

        # three stock snapshot should still exist
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 3)
        stock_1 = LogisticsCenterStockSnapshot.objects.all()[0]
        self.assertEquals(
            stock_1.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=10, minute=0, tzinfo=timezone.utc),
        )
        stock_2 = LogisticsCenterStockSnapshot.objects.all()[1]
        self.assertEquals(
            stock_2.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=11, minute=0, tzinfo=timezone.utc),
        )
        stock_3 = LogisticsCenterStockSnapshot.objects.all()[2]
        self.assertEquals(
            stock_3.snapshot_date_time,
            datetime(year=2025, month=2, day=3, hour=9, minute=0, tzinfo=timezone.utc),
        )

        # five stock snapshot lines should still exist
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 5)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.all()[0]
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 6)
        stock_line_2 = LogisticsCenterStockSnapshotLine.objects.all()[1]
        self.assertEquals(stock_line_2.stock_snapshot, stock_1)
        self.assertEquals(stock_line_2.sku, '2')
        self.assertEquals(stock_line_2.quantity, 14)
        stock_line_3 = LogisticsCenterStockSnapshotLine.objects.all()[2]
        self.assertEquals(stock_line_3.stock_snapshot, stock_2)
        self.assertEquals(stock_line_3.sku, '2')
        self.assertEquals(stock_line_3.quantity, 6)
        stock_line_4 = LogisticsCenterStockSnapshotLine.objects.all()[3]
        self.assertEquals(stock_line_4.stock_snapshot, stock_3)
        self.assertEquals(stock_line_4.sku, '1')
        self.assertEquals(stock_line_4.quantity, 7)
        stock_line_5 = LogisticsCenterStockSnapshotLine.objects.all()[4]
        self.assertEquals(stock_line_5.stock_snapshot, stock_3)
        self.assertEquals(stock_line_5.sku, '2')
        self.assertEquals(stock_line_5.quantity, 8)

        # product stock snapshot lines were not updated since the last
        # processed snapshot is an earlier-dated one
        self.product_1.refresh_from_db()
        self.product_2.refresh_from_db()
        self.assertEquals(self.product_1.logistics_snapshot_stock_line, None)
        self.assertEquals(self.product_2.logistics_snapshot_stock_line, stock_line_3)
