from datetime import datetime, timedelta, timezone
from io import BytesIO
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
    LogisticsCenterMessage,
    LogisticsCenterOrderStatus,
    LogisticsCenterStockSnapshot,
    LogisticsCenterStockSnapshotLine,
    PurchaseOrder,
    PurchaseOrderProduct,
)
from logistics.providers.orian import (
    _platform_id_to_orian_id,
    add_or_update_inbound as orian_add_or_update_inbound,
    add_or_update_outbound as orian_add_or_update_outbound,
    add_or_update_product as orian_add_or_update_product,
    add_or_update_supplier as orian_add_or_update_supplier,
)
from logistics.tasks import (
    process_logistics_center_message,
    process_logistics_center_snapshot_file,
    send_order_to_logistics_center,
    sync_product_with_logistics_center,
)


@override_settings(
    ORIAN_BASE_URL='https://test.local',
    ORIAN_API_TOKEN='1234',
    ORIAN_CONSIGNEE='AAA',
)
class OrianProviderTestCase(TestCase):
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
    def test_add_or_update_supplier_failure(self):
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Company',
            json={
                'status': None,
                'MessageID': None,
                'Note': None,
                'errorCode': 'InvalidFormatData',
                'ErrorMessage': '',
            },
            status=200,  # orian responds with status 200 even with errors
        )

        result = orian_add_or_update_supplier(self.supplier)

        # result should be false since the mock api responded with an error
        self.assertEquals(result, False)

    @responses.activate
    def test_add_or_update_supplier_success(self):
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Company',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Company Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        result = orian_add_or_update_supplier(self.supplier)

        # result should be true since we succeeded
        self.assertEquals(result, True)

    @responses.activate
    def test_add_or_update_product_failure(self):
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Sku',
            json={
                'status': None,
                'MessageID': None,
                'Note': None,
                'errorCode': 'InvalidFormatData',
                'ErrorMessage': '',
            },
            status=200,  # orian responds with status 200 even with errors
        )

        result = orian_add_or_update_product(self.product_1)

        # result should be false since the mock api responded with an error
        self.assertEquals(result, False)

    @responses.activate
    def test_add_or_update_product_success(self):
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Sku',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Sku Importer sent',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        result = orian_add_or_update_product(self.product_1)

        # result should be true since we succeeded
        self.assertEquals(result, True)

        # check that the body sent to the api contains the correct data
        self.assertEquals(len(responses.calls), 1)
        api_request_product_data = json.loads(responses.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']
        self.assertEquals(api_request_product_data['SKU'], self.product_1.sku)
        # initially the name_he field has no value so the english value should
        # be sent
        self.assertEquals(
            api_request_product_data['SKUDESCRIPTION'], 'product 1 name en'
        )
        self.assertEquals(api_request_product_data['SKUSHORTDESC'], 'product 1 name en')
        self.assertEquals(
            api_request_product_data['MANUFACTURERSKU'], self.product_1.reference
        )

        # set the hebrew name
        self.product_1.name_he = 'product 1 name he'
        self.product_1.save(update_fields=['name_he'])
        self.product_1.refresh_from_db()

        result = orian_add_or_update_product(self.product_1)

        # result should be true since we succeeded
        self.assertEquals(result, True)

        # check that the body sent to the api contains the correct data
        self.assertEquals(len(responses.calls), 2)
        api_request_product_data = json.loads(responses.calls[1].request.body)[
            'DATACOLLECTION'
        ]['DATA']
        self.assertEquals(api_request_product_data['SKU'], self.product_1.sku)
        # now the hebrew name should be sent
        self.assertEquals(
            api_request_product_data['SKUDESCRIPTION'], 'product 1 name he'
        )
        self.assertEquals(api_request_product_data['SKUSHORTDESC'], 'product 1 name he')
        self.assertEquals(
            api_request_product_data['MANUFACTURERSKU'], self.product_1.reference
        )

        # set the hebrew name to a value with quotes and apostophes
        self.product_1.name_he = 'product 1 n\'a`m"e he'
        self.product_1.save(update_fields=['name_he'])
        self.product_1.refresh_from_db()

        result = orian_add_or_update_product(self.product_1)

        # result should be true since we succeeded
        self.assertEquals(result, True)

        # check that the body sent to the api contains the correct data
        self.assertEquals(len(responses.calls), 3)
        api_request_product_data = json.loads(responses.calls[2].request.body)[
            'DATACOLLECTION'
        ]['DATA']
        self.assertEquals(api_request_product_data['SKU'], self.product_1.sku)
        # the name should be sent without apostrophes and quotes
        self.assertEquals(
            api_request_product_data['SKUDESCRIPTION'], 'product 1 name he'
        )
        self.assertEquals(api_request_product_data['SKUSHORTDESC'], 'product 1 name he')
        self.assertEquals(
            api_request_product_data['MANUFACTURERSKU'], self.product_1.reference
        )

        # set the hebrew name to a very long value
        self.product_1.name_he = (
            'product 1 name he123456789012345678901234567890123456789012345678'
            '90123456789012345678901234567890123456789012345678901234567890123'
            '45678901234567890123456789012345678901234567890123456789012345678'
            '90123456789012345678901234567890123456789012345678901234567890123'
            '4567890'
        )
        self.product_1.save(update_fields=['name_he'])
        self.product_1.refresh_from_db()

        result = orian_add_or_update_product(self.product_1)

        # result should be true since we succeeded
        self.assertEquals(result, True)

        # check that the body sent to the api contains the correct data
        self.assertEquals(len(responses.calls), 4)
        api_request_product_data = json.loads(responses.calls[3].request.body)[
            'DATACOLLECTION'
        ]['DATA']
        self.assertEquals(api_request_product_data['SKU'], self.product_1.sku)
        # trimmed versions of the product name should be sent, according to
        # orian data definitions
        self.assertEquals(len(api_request_product_data['SKUDESCRIPTION']), 255)
        self.assertEquals(
            api_request_product_data['SKUDESCRIPTION'], self.product_1.name_he[:255]
        )
        self.assertEquals(len(api_request_product_data['SKUSHORTDESC']), 150)
        self.assertEquals(
            api_request_product_data['SKUSHORTDESC'], self.product_1.name_he[:150]
        )
        self.assertEquals(
            api_request_product_data['MANUFACTURERSKU'], self.product_1.reference
        )

    @responses.activate
    def test_add_or_update_inbound_failure(self):
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Inbound',
            json={
                'status': None,
                'MessageID': None,
                'Note': None,
                'errorCode': 'InvalidFormatData',
                'ErrorMessage': '',
            },
            status=200,  # orian responds with status 200 even with errors
        )

        result = orian_add_or_update_inbound(self.purchase_order_1, datetime.now())

        # result should be false since the mock api responded with an error
        self.assertEquals(result, False)

    @responses.activate
    def test_add_or_update_inbound_success(self):
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Inbound',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Inbound Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        result = orian_add_or_update_inbound(self.purchase_order_1, datetime.now())

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
            f'{settings.ORIAN_BASE_URL}/Inbound',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Inbound Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        result = orian_add_or_update_inbound(self.purchase_order_2, datetime.now())

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
            f'{settings.ORIAN_BASE_URL}/Outbound',
            json={
                'status': None,
                'MessageID': None,
                'Note': None,
                'errorCode': 'InvalidFormatData',
                'ErrorMessage': '',
            },
            status=200,  # orian responds with status 200 even with errors
        )

        # fetch the order so manager annotated fields are included
        order = Order.objects.get(pk=self.order_1.pk)
        result = orian_add_or_update_outbound(
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
            f'{settings.ORIAN_BASE_URL}/Outbound',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Outbound Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        # fetch the order so manager annotated fields are included
        order = Order.objects.get(pk=self.order_1.pk)
        result = orian_add_or_update_outbound(
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
            f'{settings.ORIAN_BASE_URL}/Outbound',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Outbound Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        # fetch the order so manager annotated fields are included
        order = Order.objects.get(pk=self.order_2.pk)
        result = orian_add_or_update_outbound(
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
            f'{settings.ORIAN_BASE_URL}/Outbound',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Outbound Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        # fetch the order so manager annotated fields are included
        order = Order.objects.get(pk=self.order_3.pk)
        result = orian_add_or_update_outbound(
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
            _platform_id_to_orian_id(self.employee_group_campaign_2.pk),
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

        # check that the lines sent to the api contain the single product
        api_request_lines = api_request_body_json['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 1)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)
        self.assertEquals(
            api_request_lines[0]['QTYORIGINAL'],
            self.order_3.ordered_products()[0]['quantity'],
        )


@override_settings(
    ORIAN_BASE_URL='https://test.local',
    ORIAN_API_TOKEN='1234',
    ORIAN_CONSIGNEE='AAA',
    ACTIVE_LOGISTICS_CENTER=LogisticsCenterEnum.ORIAN,
)
class SendPurchaseOrderToLogisticsCenterTestCase(TestCase):
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
        self.purchase_order_1 = PurchaseOrder.objects.create(supplier=self.supplier)
        PurchaseOrderProduct.objects.create(
            product_id=self.product_1,
            purchase_order=self.purchase_order_1,
            quantity_ordered=1,
            quantity_sent_to_logistics_center=0,
        )

    @override_settings(ORIAN_MESSAGE_TIMEZONE_NAME='UTC')
    @patch('logistics.tasks.orian_add_or_update_supplier', return_value=True)
    @patch('logistics.tasks.orian_add_or_update_product', return_value=True)
    @patch('logistics.tasks.orian_add_or_update_inbound', return_value=True)
    def test_task_triggered_on_purchase_order_approve(
        self, mock_update_inbound, _mock_send_product_task, _mock_send_supplier_task
    ):
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
        PurchaseOrder.objects.create(supplier=self.supplier)
        PurchaseOrder.objects.create(
            supplier=self.supplier,
            status=PurchaseOrder.Status.PENDING.name,
        )
        PurchaseOrder.objects.create(
            supplier=self.supplier,
            status=PurchaseOrder.Status.SENT_TO_SUPPLIER.name,
        )
        PurchaseOrder.objects.create(
            supplier=self.supplier,
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
    @override_settings(ORIAN_MESSAGE_TIMEZONE_NAME='UTC')
    def test_task_api_calls(self):
        supplier_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Company',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Company Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )
        product_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Sku',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Sku Importer sent',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )
        inbound_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Inbound',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Inbound Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        # the sent_to_logistics_center_at field should be None
        self.purchase_order_1.refresh_from_db()
        self.assertEquals(self.purchase_order_1.sent_to_logistics_center_at, None)

        self.purchase_order_1.approve()

        # each mock should have been called once
        self.assertEquals(len(supplier_api_mock.calls), 1)
        self.assertEquals(len(product_api_mock.calls), 1)
        self.assertEquals(len(inbound_api_mock.calls), 1)

        # the sent_to_logistics_center_at field was set and is within the last
        # 5 seconds
        self.purchase_order_1.refresh_from_db()
        self.assertGreaterEqual(
            self.purchase_order_1.sent_to_logistics_center_at,
            datetime.now(timezone.utc) - timedelta(seconds=5),
        )


@override_settings(
    ORIAN_BASE_URL='https://test.local',
    ORIAN_API_TOKEN='1234',
    ORIAN_CONSIGNEE='AAA',
    ACTIVE_LOGISTICS_CENTER=LogisticsCenterEnum.ORIAN,
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
            sku='4,5',
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

    @responses.activate
    def test_task_add_or_update_dummy_company_failure(self):
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Company',
            json={
                'status': None,
                'MessageID': None,
                'Note': None,
                'errorCode': 'InvalidFormatData',
                'ErrorMessage': '',
            },
            status=200,  # orian responds with status 200 even with errors
        )

        with self.assertRaises(Retry):
            send_order_to_logistics_center.apply_async(
                (self.order.pk, LogisticsCenterEnum.ORIAN)
            )

    @responses.activate
    def test_task_add_or_update_outbound_failure(self):
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Company',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Company Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Outbound',
            json={
                'status': None,
                'MessageID': None,
                'Note': None,
                'errorCode': 'InvalidFormatData',
                'ErrorMessage': '',
            },
            status=200,  # orian responds with status 200 even with errors
        )

        with self.assertRaises(Retry):
            send_order_to_logistics_center.apply_async(
                (self.order.pk, LogisticsCenterEnum.ORIAN)
            )

    @responses.activate
    @override_settings(ORIAN_MESSAGE_TIMEZONE_NAME='UTC')
    def test_task_api_calls(self):
        dummy_company_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Company',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Company Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )
        outbound_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Outbound',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Outbound Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        # the status field should be pending
        self.order.refresh_from_db()
        self.assertEquals(self.order.status, Order.OrderStatusEnum.PENDING.name)

        send_order_to_logistics_center.apply_async(
            (self.order.pk, LogisticsCenterEnum.ORIAN)
        )

        # each mock should have been called once
        self.assertEquals(len(dummy_company_api_mock.calls), 1)
        self.assertEquals(len(outbound_api_mock.calls), 1)

        # the status field was set to sent to logistics center
        self.order.refresh_from_db()
        self.assertEquals(
            self.order.status,
            Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
        )

    @responses.activate
    @override_settings(ORIAN_MESSAGE_TIMEZONE_NAME='UTC')
    def test_ignore_order_products_sent_by_supplier_money(self):
        dummy_company_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Company',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Company Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )
        outbound_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Outbound',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Outbound Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        # the status field should be pending
        self.order_2.refresh_from_db()
        self.assertEquals(self.order_2.status, Order.OrderStatusEnum.PENDING.name)

        send_order_to_logistics_center.apply_async(
            (self.order_2.pk, LogisticsCenterEnum.ORIAN)
        )

        # mocks should not have been called since no order product should be
        # sent to the logistics provider
        self.assertEquals(len(dummy_company_api_mock.calls), 0)
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
            (self.order_2.pk, LogisticsCenterEnum.ORIAN)
        )

        # each mock should have been called once now
        self.assertEquals(len(dummy_company_api_mock.calls), 1)
        self.assertEquals(len(outbound_api_mock.calls), 1)

        # the status field was set to sent to logistics center
        self.order_2.refresh_from_db()
        self.assertEquals(
            self.order_2.status,
            Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
        )

        # only the regular physical product should have been sent to the
        # provider
        api_request_lines = json.loads(outbound_api_mock.calls[0].request.body)[
            'DATACOLLECTION'
        ]['DATA']['LINES']['LINE']
        self.assertEquals(len(api_request_lines), 1)
        self.assertEquals(api_request_lines[0]['SKU'], self.product_1.sku)

    @responses.activate
    @override_settings(ORIAN_MESSAGE_TIMEZONE_NAME='UTC')
    def test_order_bundle_products(self):
        dummy_company_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Company',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Company Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )
        outbound_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Outbound',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Outbound Created/Updated',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        # the status field should be pending
        self.order_3.refresh_from_db()
        self.assertEquals(self.order_3.status, Order.OrderStatusEnum.PENDING.name)

        send_order_to_logistics_center.apply_async(
            (self.order_3.pk, LogisticsCenterEnum.ORIAN)
        )

        # each mock should have been called once
        self.assertEquals(len(dummy_company_api_mock.calls), 1)
        self.assertEquals(len(outbound_api_mock.calls), 1)

        # the status field was set to sent to logistics center
        self.order_3.refresh_from_db()
        self.assertEquals(
            self.order_3.status,
            Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
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


@override_settings(
    ORIAN_BASE_URL='https://test.local',
    ORIAN_API_TOKEN='1234',
    ORIAN_CONSIGNEE='AAA',
)
class SyncProductWithLogisticsCenterTestCase(TestCase):
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

    @responses.activate
    def test_task_add_or_update_product_failure(self):
        responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Sku',
            json={
                'status': None,
                'MessageID': None,
                'Note': None,
                'errorCode': 'InvalidFormatData',
                'ErrorMessage': '',
            },
            status=200,  # orian responds with status 200 even with errors
        )

        with self.assertRaises(Retry):
            sync_product_with_logistics_center.apply_async(
                (self.product_1.pk, LogisticsCenterEnum.ORIAN)
            )

    @responses.activate
    @override_settings(ORIAN_MESSAGE_TIMEZONE_NAME='UTC')
    def test_task_api_calls(self):
        product_api_mock = responses.add(
            responses.POST,
            f'{settings.ORIAN_BASE_URL}/Sku',
            json={
                'status': 'SUCCSESS',
                'MessageID': None,
                'Note': 'Sku Importer sent',
                'errorCode': None,
                'ErrorMessage': None,
            },
            status=200,  # orian responds with status 200 even with errors
        )

        sync_product_with_logistics_center.apply_async(
            (self.product_1.pk, LogisticsCenterEnum.ORIAN)
        )

        # each mock should have been called once
        self.assertEquals(len(product_api_mock.calls), 1)


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
        self.purchase_order_1 = PurchaseOrder.objects.create(supplier=self.supplier)
        self.purchase_order_product_1 = PurchaseOrderProduct.objects.create(
            product_id=self.product_1,
            purchase_order=self.purchase_order_1,
            quantity_ordered=1,
            quantity_sent_to_logistics_center=0,
        )
        self.purchase_order_2 = PurchaseOrder.objects.create(supplier=self.supplier)
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
            center=LogisticsCenterEnum.ORIAN.name,
            message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
            raw_body='{}',
        )
        self.logistics_center_message_invalid_2 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.ORIAN.name,
            message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
            raw_body=json.dumps({'DATACOLLECTION': {'DATA': {}}}),
        )
        self.logistics_center_message_no_lines = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.ORIAN.name,
            message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
            raw_body=json.dumps(
                {
                    'DATACOLLECTION': {
                        'DATA': {
                            'RECEIPT': 'CODE1',
                            'STARTRECEIPTDATE': '8/1/2024 12:00:00 PM',
                            'CLOSERECEIPTDATE': '8/1/2024 12:00:00 PM',
                            'LINES': {'LINE': []},
                        }
                    }
                }
            ),
        )
        self.logistics_center_message_non_existing_order = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'RECEIPT': 'CODE2',
                                'STARTRECEIPTDATE': '8/1/2024 12:00:00 PM',
                                'CLOSERECEIPTDATE': '8/1/2024 12:00:00 PM',
                                'LINES': {
                                    'LINE': [
                                        {
                                            'RECEIPTLINE': '1',
                                            'CONSIGNEE': 'NKS',
                                            'SKU': '0',
                                            'ORDERID': _platform_id_to_orian_id(0),
                                            'ORDERLINE': '0',
                                            'QTYEXPECTED': '1.0000',
                                            'QTYRECEIVED': '1.0000',
                                            'QTYORIGINAL': '1.0000',
                                            'DOCUMENTTYPE': 'INBOUND',
                                            'UNITPRICE': '0',
                                            'INPUTQTY': '0.0000',
                                            'INPUTSKU': '',
                                            'INPUTUOM': '',
                                            'REFERENCEORDER': '',
                                            'REFERENCEORDERLINE': '0',
                                            'INVENTORYSTATUS': 'AVAILABLE',
                                            'COMPANY': _platform_id_to_orian_id(0),
                                            'COMPANYTYPE': 'VENDOR',
                                            'ASNS': None,
                                            'LOADS': {
                                                'LOAD': {
                                                    'LOADID': '111111111111',
                                                    'UOM': 'EACH',
                                                    'QTY': '1.0000',
                                                    'STATUS': 'AVAILABLE',
                                                    'LOADATTRIBUTES': None,
                                                }
                                            },
                                        },
                                    ]
                                },
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_single_line = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'RECEIPT': 'CODE3',
                                'STARTRECEIPTDATE': '8/1/2024 12:00:00 PM',
                                'CLOSERECEIPTDATE': '8/1/2024 12:00:00 PM',
                                'LINES': {
                                    'LINE': {
                                        'RECEIPTLINE': '1',
                                        'CONSIGNEE': 'NKS',
                                        'SKU': self.product_1.sku,
                                        'ORDERID': _platform_id_to_orian_id(
                                            self.purchase_order_1.pk
                                        ),
                                        'ORDERLINE': '0',
                                        'QTYEXPECTED': '1.0000',
                                        'QTYRECEIVED': '1.0000',
                                        'QTYORIGINAL': '1.0000',
                                        'DOCUMENTTYPE': 'INBOUND',
                                        'UNITPRICE': '0',
                                        'INPUTQTY': '0.0000',
                                        'INPUTSKU': '',
                                        'INPUTUOM': '',
                                        'REFERENCEORDER': '',
                                        'REFERENCEORDERLINE': '0',
                                        'INVENTORYSTATUS': 'AVAILABLE',
                                        'COMPANY': _platform_id_to_orian_id(
                                            self.supplier.pk
                                        ),
                                        'COMPANYTYPE': 'VENDOR',
                                        'ASNS': None,
                                        'LOADS': {
                                            'LOAD': {
                                                'LOADID': '111111111111',
                                                'UOM': 'EACH',
                                                'QTY': '1.0000',
                                                'STATUS': 'AVAILABLE',
                                                'LOADATTRIBUTES': None,
                                            }
                                        },
                                    },
                                },
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_multi_line = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'RECEIPT': 'CODE4',
                                'STARTRECEIPTDATE': '8/1/2024 12:00:00 PM',
                                'CLOSERECEIPTDATE': '8/1/2024 12:00:00 PM',
                                'LINES': {
                                    'LINE': [
                                        {
                                            'RECEIPTLINE': '1',
                                            'CONSIGNEE': 'NKS',
                                            'SKU': self.product_1.sku,
                                            'ORDERID': _platform_id_to_orian_id(
                                                self.purchase_order_2.pk
                                            ),
                                            'ORDERLINE': '0',
                                            'QTYEXPECTED': '3.0000',
                                            'QTYRECEIVED': '3.0000',
                                            'QTYORIGINAL': '3.0000',
                                            'DOCUMENTTYPE': 'INBOUND',
                                            'UNITPRICE': '0',
                                            'INPUTQTY': '0.0000',
                                            'INPUTSKU': '',
                                            'INPUTUOM': '',
                                            'REFERENCEORDER': '',
                                            'REFERENCEORDERLINE': '0',
                                            'INVENTORYSTATUS': 'AVAILABLE',
                                            'COMPANY': _platform_id_to_orian_id(
                                                self.supplier.pk
                                            ),
                                            'COMPANYTYPE': 'VENDOR',
                                            'ASNS': None,
                                            'LOADS': {
                                                'LOAD': {
                                                    'LOADID': '111111111111',
                                                    'UOM': 'EACH',
                                                    'QTY': '3.0000',
                                                    'STATUS': 'AVAILABLE',
                                                    'LOADATTRIBUTES': None,
                                                }
                                            },
                                        },
                                        {
                                            'RECEIPTLINE': '2',
                                            'CONSIGNEE': 'NKS',
                                            'SKU': self.product_2.sku,
                                            'ORDERID': _platform_id_to_orian_id(
                                                self.purchase_order_2.pk
                                            ),
                                            'ORDERLINE': '1',
                                            'QTYEXPECTED': '15.0000',
                                            'QTYRECEIVED': '15.0000',
                                            'QTYORIGINAL': '15.0000',
                                            'DOCUMENTTYPE': 'INBOUND',
                                            'UNITPRICE': '0',
                                            'INPUTQTY': '0.0000',
                                            'INPUTSKU': '',
                                            'INPUTUOM': '',
                                            'REFERENCEORDER': '',
                                            'REFERENCEORDERLINE': '0',
                                            'INVENTORYSTATUS': 'AVAILABLE',
                                            'COMPANY': _platform_id_to_orian_id(
                                                self.supplier.pk
                                            ),
                                            'COMPANYTYPE': 'VENDOR',
                                            'ASNS': None,
                                            'LOADS': {
                                                'LOAD': {
                                                    'LOADID': '111111111111',
                                                    'UOM': 'EACH',
                                                    'QTY': '15.0000',
                                                    'STATUS': 'AVAILABLE',
                                                    'LOADATTRIBUTES': None,
                                                }
                                            },
                                        },
                                    ]
                                },
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_multi_line_quantity_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'RECEIPT': 'CODE4',
                                'STARTRECEIPTDATE': '8/2/2024 4:00:00 PM',
                                'CLOSERECEIPTDATE': '8/2/2024 4:00:00 PM',
                                'LINES': {
                                    'LINE': [
                                        {
                                            'RECEIPTLINE': '1',
                                            'CONSIGNEE': 'NKS',
                                            'SKU': self.product_1.sku,
                                            'ORDERID': _platform_id_to_orian_id(
                                                self.purchase_order_2.pk
                                            ),
                                            'ORDERLINE': '0',
                                            'QTYEXPECTED': '30.0000',
                                            'QTYRECEIVED': '30.0000',
                                            'QTYORIGINAL': '30.0000',
                                            'DOCUMENTTYPE': 'INBOUND',
                                            'UNITPRICE': '0',
                                            'INPUTQTY': '0.0000',
                                            'INPUTSKU': '',
                                            'INPUTUOM': '',
                                            'REFERENCEORDER': '',
                                            'REFERENCEORDERLINE': '0',
                                            'INVENTORYSTATUS': 'AVAILABLE',
                                            'COMPANY': _platform_id_to_orian_id(
                                                self.supplier.pk
                                            ),
                                            'COMPANYTYPE': 'VENDOR',
                                            'ASNS': None,
                                            'LOADS': {
                                                'LOAD': {
                                                    'LOADID': '111111111111',
                                                    'UOM': 'EACH',
                                                    'QTY': '30.0000',
                                                    'STATUS': 'AVAILABLE',
                                                    'LOADATTRIBUTES': None,
                                                }
                                            },
                                        },
                                        {
                                            'RECEIPTLINE': '2',
                                            'CONSIGNEE': 'NKS',
                                            'SKU': self.product_2.sku,
                                            'ORDERID': _platform_id_to_orian_id(
                                                self.purchase_order_2.pk
                                            ),
                                            'ORDERLINE': '1',
                                            'QTYEXPECTED': '150.0000',
                                            'QTYRECEIVED': '150.0000',
                                            'QTYORIGINAL': '150.0000',
                                            'DOCUMENTTYPE': 'INBOUND',
                                            'UNITPRICE': '0',
                                            'INPUTQTY': '0.0000',
                                            'INPUTSKU': '',
                                            'INPUTUOM': '',
                                            'REFERENCEORDER': '',
                                            'REFERENCEORDERLINE': '0',
                                            'INVENTORYSTATUS': 'AVAILABLE',
                                            'COMPANY': _platform_id_to_orian_id(
                                                self.supplier.pk
                                            ),
                                            'COMPANYTYPE': 'VENDOR',
                                            'ASNS': None,
                                            'LOADS': {
                                                'LOAD': {
                                                    'LOADID': '111111111111',
                                                    'UOM': 'EACH',
                                                    'QTY': '150.0000',
                                                    'STATUS': 'AVAILABLE',
                                                    'LOADATTRIBUTES': None,
                                                }
                                            },
                                        },
                                    ]
                                },
                            }
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
            datetime(year=2024, month=8, day=1, hour=9, minute=0, tzinfo=timezone.utc),
        )
        self.assertEquals(
            receipt.receipt_close_date,
            datetime(year=2024, month=8, day=1, hour=9, minute=0, tzinfo=timezone.utc),
        )

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
            datetime(year=2024, month=8, day=2, hour=13, minute=0, tzinfo=timezone.utc),
        )
        self.assertEquals(
            receipt.receipt_close_date,
            datetime(year=2024, month=8, day=2, hour=13, minute=0, tzinfo=timezone.utc),
        )

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
        )
        OrderProduct.objects.create(
            order_id=self.order,
            product_id=employee_group_campaign_product,
            quantity=1,
        )

        self.logistics_center_message_invalid_1 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.ORIAN.name,
            message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
            raw_body='{}',
        )
        self.logistics_center_message_invalid_2 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.ORIAN.name,
            message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
            raw_body=json.dumps({'DATACOLLECTION': {'DATA': {}}}),
        )
        self.logistics_center_message_non_existing_order = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'CONSIGNEE': 'NKS',
                                'ORDERID': 'unknown',
                                'ORDERTYPE': 'CUSTOMER',
                                'TOSTATUS': 'RECEIVED',
                                'STATUSDATE': '8/1/2024 12:00:00 PM',
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_order_picked_status_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'CONSIGNEE': 'NKS',
                                'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                                'ORDERTYPE': 'CUSTOMER',
                                'TOSTATUS': 'PICKED',
                                'STATUSDATE': '8/1/2024 12:00:00 PM',
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_order_transported_status_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'CONSIGNEE': 'NKS',
                                'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                                'ORDERTYPE': 'CUSTOMER',
                                'TOSTATUS': 'TRANSPORTED',
                                'STATUSDATE': '8/2/2024 12:00:00 PM',
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_order_received_late_status_update = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'CONSIGNEE': 'NKS',
                                'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                                'ORDERTYPE': 'CUSTOMER',
                                'TOSTATUS': 'RECEIVED',
                                'STATUSDATE': '8/1/2024 06:00:00 AM',
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_order_picked_status_update_deprecated_id = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'CONSIGNEE': 'NKS',
                                'ORDERID': _platform_id_to_orian_id(self.order.pk),
                                'ORDERTYPE': 'CUSTOMER',
                                'TOSTATUS': 'PICKED',
                                'STATUSDATE': '8/1/2024 12:00:00 PM',
                            }
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

    def test_order_id_not_found(self):
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

    def test_order_successful_status_updates_deprecated_id(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_order_picked_status_update_deprecated_id.pk,)
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
        )
        OrderProduct.objects.create(
            order_id=self.order,
            product_id=employee_group_campaign_product,
            quantity=1,
        )

        self.logistics_center_message_invalid_1 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.ORIAN.name,
            message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
            raw_body='{}',
        )
        self.logistics_center_message_invalid_2 = LogisticsCenterMessage.objects.create(
            center=LogisticsCenterEnum.ORIAN.name,
            message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
            raw_body=json.dumps({'DATACOLLECTION': {'DATA': {}}}),
        )
        self.logistics_center_message_non_existing_order = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'CONSIGNEE': 'NKS',
                                'ORDERID': 'unknown',
                                'ORDERTYPE': 'CUSTOMER',
                                'TARGETCOMPANY': _platform_id_to_orian_id(
                                    settings.ORIAN_DUMMY_CUSTOMER_PLATFORM_ID
                                ),
                                'COMPANYTYPE': 'CUSTOMER',
                                'STATUS': 'SHIPPED',
                                'SHIPPEDDATE': '8/1/2024 12:00:00 PM',
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_ship_order = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'CONSIGNEE': 'NKS',
                                'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                                'ORDERTYPE': 'CUSTOMER',
                                'TARGETCOMPANY': _platform_id_to_orian_id(
                                    settings.ORIAN_DUMMY_CUSTOMER_PLATFORM_ID
                                ),
                                'COMPANYTYPE': 'CUSTOMER',
                                'STATUS': 'SHIPPED',
                                'SHIPPEDDATE': '8/1/2024 12:00:00 PM',
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_ship_order_late = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'CONSIGNEE': 'NKS',
                                'ORDERID': Order.objects.get(pk=self.order.pk).order_id,
                                'ORDERTYPE': 'CUSTOMER',
                                'TARGETCOMPANY': _platform_id_to_orian_id(
                                    settings.ORIAN_DUMMY_CUSTOMER_PLATFORM_ID
                                ),
                                'COMPANYTYPE': 'CUSTOMER',
                                'STATUS': 'SHIPPEDAGAIN',
                                'SHIPPEDDATE': '8/1/2024 06:00:00 AM',
                            }
                        }
                    }
                ),
            )
        )
        self.logistics_center_message_ship_order_deprecated_id = (
            LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
                raw_body=json.dumps(
                    {
                        'DATACOLLECTION': {
                            'DATA': {
                                'CONSIGNEE': 'NKS',
                                'ORDERID': _platform_id_to_orian_id(self.order.pk),
                                'ORDERTYPE': 'CUSTOMER',
                                'TARGETCOMPANY': _platform_id_to_orian_id(
                                    settings.ORIAN_DUMMY_CUSTOMER_PLATFORM_ID
                                ),
                                'COMPANYTYPE': 'CUSTOMER',
                                'STATUS': 'SHIPPED',
                                'SHIPPEDDATE': '8/1/2024 12:00:00 PM',
                            }
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

        process_logistics_center_message.apply_async(
            (self.logistics_center_message_ship_order.pk,)
        )

        # receiving a ship order again should not create another order
        # status record
        self.assertEquals(len(LogisticsCenterOrderStatus.objects.all()), 2)

    def test_order_successful_status_updates_deprecated_id(self):
        process_logistics_center_message.apply_async(
            (self.logistics_center_message_ship_order_deprecated_id.pk,)
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

        # test snapshot files
        self.logistics_center_snapshot_no_lines = (
            b'<DATACOLLECTION><ANYNONDATAVALUE/></DATACOLLECTION>'
        )
        self.logistics_center_snapshot_single_line = (
            b'<DATACOLLECTION><DATA><CONSIGNEE>NKS</CONSIGNEE><SKU>1</SKU>'
            b'<QTY>1.0000</QTY></DATA></DATACOLLECTION>'
        )
        self.logistics_center_snapshot_multi_line = (
            b'<DATACOLLECTION><DATA><CONSIGNEE>NKS</CONSIGNEE><SKU>1</SKU>'
            b'<QTY>2.0000</QTY></DATA><DATA><CONSIGNEE>NKS</CONSIGNEE>'
            b'<SKU>2</SKU><QTY>3.0000</QTY></DATA><DATA>'
            b'<CONSIGNEE>NKS</CONSIGNEE><SKU>3</SKU><QTY>15.0000</QTY></DATA>'
            b'</DATACOLLECTION>'
        )
        self.logistics_center_snapshot_updates_1 = (
            b'<DATACOLLECTION><DATA><CONSIGNEE>NKS</CONSIGNEE><SKU>1</SKU>'
            b'<QTY>4.0000</QTY></DATA><DATA><CONSIGNEE>NKS</CONSIGNEE>'
            b'<SKU>2</SKU><QTY>5.0000</QTY></DATA></DATACOLLECTION>'
        )
        self.logistics_center_snapshot_updates_2 = (
            b'<DATACOLLECTION><DATA><CONSIGNEE>NKS</CONSIGNEE><SKU>2</SKU>'
            b'<QTY>6.0000</QTY></DATA></DATACOLLECTION>'
        )
        self.logistics_center_snapshot_updates_3 = (
            b'<DATACOLLECTION><DATA><CONSIGNEE>NKS</CONSIGNEE><SKU>1</SKU>'
            b'<QTY>7.0000</QTY></DATA><DATA><CONSIGNEE>NKS</CONSIGNEE>'
            b'<SKU>2</SKU><QTY>8.0000</QTY></DATA></DATACOLLECTION>'
        )

    @patch('django.core.files.storage.FileSystemStorage.exists')
    def test_snapshot_file_not_found(self, mock_exists):
        mock_exists.return_value = False

        process_result = process_logistics_center_snapshot_file.apply_async(
            (
                LogisticsCenterEnum.ORIAN.name,
                'non_existing_path.xml',
                datetime.now(),
            )
        )

        # processing was not successful
        self.assertEquals(process_result.result, False)

        # no stock snapshots were created
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 0)

    @patch('django.core.files.storage.FileSystemStorage.exists')
    @patch('django.core.files.storage.FileSystemStorage.open')
    def test_empty_snapshot_file(self, mock_open, mock_exists):
        mock_exists.return_value = True
        mock_open.return_value = BytesIO(self.logistics_center_snapshot_no_lines)

        process_result = process_logistics_center_snapshot_file.apply_async(
            (
                LogisticsCenterEnum.ORIAN.name,
                'no_lines_path.xml',
                datetime.now(),
            )
        )

        # processing was successful
        self.assertEquals(process_result.result, True)

        # one stock snapshot was created
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 1)
        self.assertEquals(
            LogisticsCenterStockSnapshot.objects.first().snapshot_file_path,
            'no_lines_path.xml',
        )

        # no stock snapshot lines were created
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 0)

    @patch('django.core.files.storage.FileSystemStorage.exists')
    @patch('django.core.files.storage.FileSystemStorage.open')
    def test_snapshot_file_single_line(self, mock_open, mock_exists):
        mock_exists.return_value = True
        mock_open.return_value = BytesIO(self.logistics_center_snapshot_single_line)

        process_result = process_logistics_center_snapshot_file.apply_async(
            (
                LogisticsCenterEnum.ORIAN.name,
                'single_line_path.xml',
                datetime.now(),
            )
        )

        # processing was successful
        self.assertEquals(process_result.result, True)

        # one stock snapshot was created
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 1)
        stock_1 = LogisticsCenterStockSnapshot.objects.first()
        self.assertEquals(stock_1.snapshot_file_path, 'single_line_path.xml')

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

    @patch('django.core.files.storage.FileSystemStorage.exists')
    @patch('django.core.files.storage.FileSystemStorage.open')
    def test_snapshot_file_multi_line(self, mock_open, mock_exists):
        mock_exists.return_value = True
        mock_open.return_value = BytesIO(self.logistics_center_snapshot_multi_line)

        process_result = process_logistics_center_snapshot_file.apply_async(
            (
                LogisticsCenterEnum.ORIAN.name,
                'multi_line_path.xml',
                datetime.now(),
            )
        )

        # processing was successful
        self.assertEquals(process_result.result, True)

        # one stock snapshot was created
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 1)
        stock_1 = LogisticsCenterStockSnapshot.objects.first()
        self.assertEquals(stock_1.snapshot_file_path, 'multi_line_path.xml')

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

    @patch('django.core.files.storage.FileSystemStorage.exists')
    @patch('django.core.files.storage.FileSystemStorage.open')
    def test_snapshot_file_updates(self, mock_open, mock_exists):
        mock_exists.return_value = True
        mock_open.return_value = BytesIO(self.logistics_center_snapshot_updates_1)

        first_snapshot_date_time = datetime.now()
        process_result = process_logistics_center_snapshot_file.apply_async(
            (
                LogisticsCenterEnum.ORIAN.name,
                'updates_1_path.xml',
                first_snapshot_date_time,
            )
        )

        # processing was successful
        self.assertEquals(process_result.result, True)

        # one stock snapshot was created
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 1)
        stock_1 = LogisticsCenterStockSnapshot.objects.first()
        self.assertEquals(stock_1.snapshot_file_path, 'updates_1_path.xml')

        # two stock snapshot lines were created
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 2)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.all()[0]
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 4)
        stock_line_2 = LogisticsCenterStockSnapshotLine.objects.all()[1]
        self.assertEquals(stock_line_2.stock_snapshot, stock_1)
        self.assertEquals(stock_line_2.sku, '2')
        self.assertEquals(stock_line_2.quantity, 5)

        # the correct products were linked to the stock snapshot line
        self.product_1.refresh_from_db()
        self.product_2.refresh_from_db()
        self.assertEquals(self.product_1.logistics_snapshot_stock_line, stock_line_1)
        self.assertEquals(self.product_2.logistics_snapshot_stock_line, stock_line_2)

        mock_open.return_value = BytesIO(self.logistics_center_snapshot_updates_2)

        # process the second snapshot
        process_result = process_logistics_center_snapshot_file.apply_async(
            (
                LogisticsCenterEnum.ORIAN.name,
                'updates_2_path.xml',
                datetime.now(),
            )
        )

        # processing was successful
        self.assertEquals(process_result.result, True)

        # two stock snapshot should now exist
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 2)
        stock_1 = LogisticsCenterStockSnapshot.objects.all()[0]
        self.assertEquals(stock_1.snapshot_file_path, 'updates_1_path.xml')
        stock_2 = LogisticsCenterStockSnapshot.objects.all()[1]
        self.assertEquals(stock_2.snapshot_file_path, 'updates_2_path.xml')

        # three stock snapshot lines should now exist
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 3)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.all()[0]
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 4)
        stock_line_2 = LogisticsCenterStockSnapshotLine.objects.all()[1]
        self.assertEquals(stock_line_2.stock_snapshot, stock_1)
        self.assertEquals(stock_line_2.sku, '2')
        self.assertEquals(stock_line_2.quantity, 5)
        stock_line_3 = LogisticsCenterStockSnapshotLine.objects.all()[2]
        self.assertEquals(stock_line_3.stock_snapshot, stock_2)
        self.assertEquals(stock_line_3.sku, '2')
        self.assertEquals(stock_line_3.quantity, 6)

        # the correct products were linked to the stock snapshot line
        self.product_1.refresh_from_db()
        self.product_2.refresh_from_db()
        self.assertEquals(self.product_1.logistics_snapshot_stock_line, None)
        self.assertEquals(self.product_2.logistics_snapshot_stock_line, stock_line_3)

        mock_open.return_value = BytesIO(self.logistics_center_snapshot_updates_3)

        # process the third snapshot - which has an earlier date time than the
        # previously-processed snapshots
        process_result = process_logistics_center_snapshot_file.apply_async(
            (
                LogisticsCenterEnum.ORIAN.name,
                'updates_3_path.xml',
                datetime.now() - timedelta(hours=1),
            )
        )

        # processing was successful
        self.assertEquals(process_result.result, True)

        # three stock snapshot should now exist
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 3)
        stock_1 = LogisticsCenterStockSnapshot.objects.all()[0]
        self.assertEquals(stock_1.snapshot_file_path, 'updates_1_path.xml')
        stock_2 = LogisticsCenterStockSnapshot.objects.all()[1]
        self.assertEquals(stock_2.snapshot_file_path, 'updates_2_path.xml')
        stock_3 = LogisticsCenterStockSnapshot.objects.all()[2]
        self.assertEquals(stock_3.snapshot_file_path, 'updates_3_path.xml')

        # five stock snapshot lines should now exist
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 5)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.all()[0]
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 4)
        stock_line_2 = LogisticsCenterStockSnapshotLine.objects.all()[1]
        self.assertEquals(stock_line_2.stock_snapshot, stock_1)
        self.assertEquals(stock_line_2.sku, '2')
        self.assertEquals(stock_line_2.quantity, 5)
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

        mock_open.return_value = BytesIO(self.logistics_center_snapshot_updates_1)

        # process the first snapshot - data should be updated and new stock
        # records should not be created
        process_result = process_logistics_center_snapshot_file.apply_async(
            (
                LogisticsCenterEnum.ORIAN.name,
                'updates_1_path.xml',
                first_snapshot_date_time,
            )
        )

        # processing was successful
        self.assertEquals(process_result.result, True)

        # three stock snapshot should still exist
        self.assertEquals(len(LogisticsCenterStockSnapshot.objects.all()), 3)
        stock_1 = LogisticsCenterStockSnapshot.objects.all()[0]
        self.assertEquals(stock_1.snapshot_file_path, 'updates_1_path.xml')
        stock_2 = LogisticsCenterStockSnapshot.objects.all()[1]
        self.assertEquals(stock_2.snapshot_file_path, 'updates_2_path.xml')
        stock_3 = LogisticsCenterStockSnapshot.objects.all()[2]
        self.assertEquals(stock_3.snapshot_file_path, 'updates_3_path.xml')

        # five stock snapshot lines should still exist
        self.assertEquals(len(LogisticsCenterStockSnapshotLine.objects.all()), 5)
        stock_line_1 = LogisticsCenterStockSnapshotLine.objects.all()[0]
        self.assertEquals(stock_line_1.stock_snapshot, stock_1)
        self.assertEquals(stock_line_1.sku, '1')
        self.assertEquals(stock_line_1.quantity, 4)
        stock_line_2 = LogisticsCenterStockSnapshotLine.objects.all()[1]
        self.assertEquals(stock_line_2.stock_snapshot, stock_1)
        self.assertEquals(stock_line_2.sku, '2')
        self.assertEquals(stock_line_2.quantity, 5)
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
