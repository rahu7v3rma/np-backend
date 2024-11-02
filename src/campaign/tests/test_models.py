from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

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
from inventory.models import (
    Brand,
    Product,
    ProductBundleItem,
    Supplier,
)


User = get_user_model()


class OrderModelTestCase(TestCase):
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
            cost_price=10,
            sale_price=20,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.PHYSICAL.name,
        )
        self.product_2 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 2 name',
            sku='2',
            cost_price=30,
            sale_price=40,
            product_type=Product.ProductTypeEnum.SENT_BY_SUPPLIER.name,
            product_kind=Product.ProductKindEnum.PHYSICAL.name,
        )
        self.product_3 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 3 name',
            sku='3',
            cost_price=50,
            sale_price=60,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.MONEY.name,
        )
        self.product_4 = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            name='product 4 name',
            sku='2,3',
            cost_price=80,
            sale_price=100,
            product_type=Product.ProductTypeEnum.REGULAR.name,
            product_kind=Product.ProductKindEnum.BUNDLE.name,
        )
        ProductBundleItem.objects.create(
            bundle=self.product_4,
            product=self.product_2,
            quantity=1,
        )
        ProductBundleItem.objects.create(
            bundle=self.product_4,
            product=self.product_3,
            quantity=3,
        )

        # create the campaign infrastructure for the orders we need
        organization = Organization.objects.create(
            name='Test organization',
            manager_full_name='Test manager',
            manager_phone_number='0500000009',
            manager_email='manager@test.test',
        )
        self.campaign = Campaign.objects.create(
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
            employee_group=employee_group,
            campaign=self.campaign,
            budget_per_employee=100,
        )
        self.employee = Employee.objects.create(
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
        self.employee_group_campaign_product_4 = (
            EmployeeGroupCampaignProduct.objects.create(
                employee_group_campaign_id=employee_group_campaign,
                product_id=self.product_4,
            )
        )

    def test_ordered_products_no_products(self):
        order = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=self.campaign, employee=self.employee
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

        ordered_products = order.ordered_products()
        self.assertEquals(len(ordered_products), 0)

    def test_ordered_products_single_product(self):
        order = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=self.campaign, employee=self.employee
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
            order_id=order,
            product_id=self.employee_group_campaign_product_1,
            quantity=1,
        )

        ordered_products = order.ordered_products()
        self.assertEquals(len(ordered_products), 1)
        self.assertEquals(ordered_products[0]['sku'], self.product_1.sku)
        self.assertEquals(ordered_products[0]['quantity'], 1)

    def test_ordered_products_single_bundle_product(self):
        order = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=self.campaign, employee=self.employee
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
            order_id=order,
            product_id=self.employee_group_campaign_product_4,
            quantity=2,
        )

        # ordered products should contain the bundled products and not the
        # bundle product
        ordered_products = order.ordered_products()
        self.assertEquals(len(ordered_products), 2)
        self.assertEquals(ordered_products[0]['sku'], self.product_2.sku)
        self.assertEquals(ordered_products[0]['quantity'], 2)
        self.assertEquals(ordered_products[1]['sku'], self.product_3.sku)
        self.assertEquals(ordered_products[1]['quantity'], 6)

    def test_ordered_products_multiple_products(self):
        order = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.get(
                campaign=self.campaign, employee=self.employee
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
            order_id=order,
            product_id=self.employee_group_campaign_product_1,
            quantity=3,
        )
        OrderProduct.objects.create(
            order_id=order,
            product_id=self.employee_group_campaign_product_4,
            quantity=4,
        )

        # ordered products should contain the bundled products and not the
        # bundle product
        ordered_products = order.ordered_products()
        self.assertEquals(len(ordered_products), 3)
        self.assertEquals(ordered_products[0]['sku'], self.product_1.sku)
        self.assertEquals(ordered_products[0]['quantity'], 3)
        self.assertEquals(ordered_products[1]['sku'], self.product_2.sku)
        self.assertEquals(ordered_products[1]['quantity'], 4)
        self.assertEquals(ordered_products[2]['sku'], self.product_3.sku)
        self.assertEquals(ordered_products[2]['quantity'], 12)
