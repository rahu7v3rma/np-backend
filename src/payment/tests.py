from datetime import datetime, timedelta, timezone
import json
import urllib.parse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
import responses
from rest_framework.test import APIClient

from campaign.models import (
    Campaign,
    CampaignEmployee,
    Employee,
    EmployeeGroup,
    Order,
    Organization,
)
from inventory.models import Brand, Category, Product, Supplier, Tag
from payment.models import PaymentInformation


User = get_user_model()


@override_settings(GROW_WEBHOOK_SECRET='verysecret')
class PaymentWebhookViewTest(TestCase):
    """
    Test case to check payment APIs
    """

    def setUp(self):
        self.route = '/payment/payment-detail/'
        self.payment_route = '/payment/create-payment/{product_id}'
        self.client = APIClient()
        self.employee_group = EmployeeGroup.objects.create(name='employee_group')
        self.employee = Employee.objects.create(
            first_name='John',
            last_name='Smith',
            phone_number='0509721696',
            auth_id='employee_auth_id',
            active=True,
            employee_group=EmployeeGroup.objects.first(),
        )
        self.admin = User.objects.create(
            email='admin@domain.com',
            username='admin_username',
            password='admin_password',
            is_staff=True,
        )
        self.category = Category.objects.create(name='nicklas', icon_image='test.jpg')
        self.category2 = Category.objects.create(
            name='category2',
            name_en='category2 en',
            name_he='category2 he',
            icon_image='icon2.jpg',
        )

        self.brand = Brand.objects.create(name='test_brand', logo_image='logo.jpg')
        self.supplier = Supplier.objects.create(
            name='supplier',
            address_city='New york',
            address_street='R1 block',
            address_street_number='street # 6',
            email='supplier@gmail.com',
        )
        self.tag = Tag.objects.create(name='product_tag')
        self.product = Product.objects.create(
            brand=self.brand,
            supplier=self.supplier,
            reference='ad',
            sale_price=1200,
            name='laptop',
            product_kind='MONEY',
            product_type='REGULAR',
            description='good quality',
            sku='1234',
            active=True,
            cost_price=1500,
            delivery_price=100,
        )
        self.product.categories.add(self.category)
        self.product.categories.add(self.category2)
        self.product.tags.add(self.tag)
        self.organization = Organization.objects.create(
            name='Test',
            manager_full_name='test',
            manager_phone_number='086786',
            manager_email='info@gmail.com',
        )
        self.organization.products.add(self.product, through_defaults={'price': 3000})
        self.campaign = Campaign.objects.create(
            organization=self.organization,
            name='campaign',
            start_date_time=datetime.now(timezone.utc),
            end_date_time=datetime.now(timezone.utc) + timedelta(days=7),
            status=Campaign.CampaignStatusEnum.ACTIVE.name,
            login_page_title='',
            login_page_subtitle='',
            main_page_first_banner_title='',
            main_page_first_banner_subtitle='',
            main_page_first_banner_image='',
            main_page_first_banner_mobile_image='',
            main_page_second_banner_title='',
            main_page_second_banner_subtitle='',
            main_page_second_banner_background_color='',
            main_page_second_banner_text_color='',
            sms_sender_name='',
            sms_welcome_text='',
            email_welcome_text='',
        )
        self.campaign_employee = CampaignEmployee.objects.create(
            campaign=self.campaign, employee=self.employee
        )
        self.order = Order.objects.create(
            campaign_employee_id=self.campaign_employee,
            order_date_time=datetime.now(timezone.utc),
            cost_from_budget=100,
            cost_added=50,
            full_name='John Smith',
            phone_number='0509721696',
            status=Order.OrderStatusEnum.INCOMPLETE.name,
        )
        self.payment_info = PaymentInformation.objects.create(
            order=self.order,
            process_token='f01644c3f19b30h825eg5g5g5g3b0',
            process_id=123,
            amount=100,
            is_paid=False,
        )

    def test_webhook_no_secret(self):
        # no secret
        response = self.client.post(
            self.route,
            data=urllib.parse.urlencode(
                {
                    'err': '',
                    'status': '1',
                    'data[processId]': self.payment_info.process_id,
                    'data[statusCode]': '2',
                    'data[asmachta]': '123',
                    'data[cardSuffix]': '0000',
                    'data[cardType]': 'Local',
                    'data[cardTypeCode]': '1',
                    'data[cardBrand]': 'Visa',
                    'data[cardBrandCode]': '3',
                    'data[cardExp]': '1224',
                    'data[firstPaymentSum]': '0',
                    'data[periodicalPaymentSum]': '0',
                    'data[status]': '\u05e9\u05d5\u05dc\u05dd',
                    'data[transactionTypeId]': '1',
                    'data[paymentType]': '2',
                    'data[sum]': '40',
                    'data[paymentsNum]': '0',
                    'data[allPaymentsNum]': '1',
                    'data[paymentDate]': '31/7/24',
                    'data[description]': 'Blender x 1',
                    'data[fullName]': 'Full Name',
                    'data[payerPhone]': '0000000000',
                    'data[payerEmail]': '',
                    'data[transactionId]': '100',
                    'data[transactionToken]': 'abcd',
                    'data[processToken]': 'abcd',
                },
            ),
            content_type='application/x-www-form-urlencoded',
        )
        content = json.loads(response.content.decode(encoding='UTF-8'))

        # response is always successfull
        self.assertDictEqual(
            content,
            {
                'success': True,
                'status': 200,
                'data': {},
            },
        )

        # order is not paid yet
        self.payment_info.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment_info.is_paid, False)
        self.assertEqual(self.order.status, Order.OrderStatusEnum.INCOMPLETE.name)

    def test_webhook_bad_secret(self):
        # no secret
        response = self.client.post(
            self.route,
            data=urllib.parse.urlencode(
                {
                    'err': '',
                    'status': '1',
                    'data[processId]': self.payment_info.process_id,
                    'data[customFields][cField1]': 'wrong',
                    'data[statusCode]': '2',
                    'data[asmachta]': '123',
                    'data[cardSuffix]': '0000',
                    'data[cardType]': 'Local',
                    'data[cardTypeCode]': '1',
                    'data[cardBrand]': 'Visa',
                    'data[cardBrandCode]': '3',
                    'data[cardExp]': '1224',
                    'data[firstPaymentSum]': '0',
                    'data[periodicalPaymentSum]': '0',
                    'data[status]': '\u05e9\u05d5\u05dc\u05dd',
                    'data[transactionTypeId]': '1',
                    'data[paymentType]': '2',
                    'data[sum]': '40',
                    'data[paymentsNum]': '0',
                    'data[allPaymentsNum]': '1',
                    'data[paymentDate]': '31/7/24',
                    'data[description]': 'Blender x 1',
                    'data[fullName]': 'Full Name',
                    'data[payerPhone]': '0000000000',
                    'data[payerEmail]': '',
                    'data[transactionId]': '100',
                    'data[transactionToken]': 'abcd',
                    'data[processToken]': 'abcd',
                },
            ),
            content_type='application/x-www-form-urlencoded',
        )
        content = json.loads(response.content.decode(encoding='UTF-8'))

        # response is always successfull
        self.assertDictEqual(
            content,
            {
                'success': True,
                'status': 200,
                'data': {},
            },
        )

        # order is not paid yet
        self.payment_info.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment_info.is_paid, False)
        self.assertEqual(self.order.status, Order.OrderStatusEnum.INCOMPLETE.name)

    def test_webhook_payment_not_found(self):
        response = self.client.post(
            self.route,
            data=urllib.parse.urlencode(
                {
                    'err': '',
                    'status': '1',
                    'data[processId]': 1,
                    'data[customFields][cField1]': 'verysecret',
                    'data[statusCode]': '2',
                    'data[asmachta]': '123',
                    'data[cardSuffix]': '0000',
                    'data[cardType]': 'Local',
                    'data[cardTypeCode]': '1',
                    'data[cardBrand]': 'Visa',
                    'data[cardBrandCode]': '3',
                    'data[cardExp]': '1224',
                    'data[firstPaymentSum]': '0',
                    'data[periodicalPaymentSum]': '0',
                    'data[status]': '\u05e9\u05d5\u05dc\u05dd',
                    'data[transactionTypeId]': '1',
                    'data[paymentType]': '2',
                    'data[sum]': '40',
                    'data[paymentsNum]': '0',
                    'data[allPaymentsNum]': '1',
                    'data[paymentDate]': '31/7/24',
                    'data[description]': 'Blender x 1',
                    'data[fullName]': 'Full Name',
                    'data[payerPhone]': '0000000000',
                    'data[payerEmail]': '',
                    'data[transactionId]': '100',
                    'data[transactionToken]': 'abcd',
                    'data[processToken]': 'abcd',
                },
            ),
            content_type='application/x-www-form-urlencoded',
        )
        content = json.loads(response.content.decode(encoding='UTF-8'))

        # response is always successfull
        self.assertDictEqual(
            content,
            {
                'success': True,
                'status': 200,
                'data': {},
            },
        )

        # order is not paid yet
        self.payment_info.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment_info.is_paid, False)
        self.assertEqual(self.order.status, Order.OrderStatusEnum.INCOMPLETE.name)

    def test_webhook_payment_already_paid(self):
        # set the order to be paid
        self.payment_info.is_paid = True
        self.order.status = Order.OrderStatusEnum.PENDING.name
        self.payment_info.save()
        self.order.save()
        self.payment_info.refresh_from_db()
        self.order.refresh_from_db()

        response = self.client.post(
            self.route,
            data=urllib.parse.urlencode(
                {
                    'err': '',
                    'status': '1',
                    'data[processId]': self.payment_info.process_id,
                    'data[customFields][cField1]': 'verysecret',
                    'data[statusCode]': '2',
                    'data[asmachta]': '123',
                    'data[cardSuffix]': '0000',
                    'data[cardType]': 'Local',
                    'data[cardTypeCode]': '1',
                    'data[cardBrand]': 'Visa',
                    'data[cardBrandCode]': '3',
                    'data[cardExp]': '1224',
                    'data[firstPaymentSum]': '0',
                    'data[periodicalPaymentSum]': '0',
                    'data[status]': '\u05e9\u05d5\u05dc\u05dd',
                    'data[transactionTypeId]': '1',
                    'data[paymentType]': '2',
                    'data[sum]': '40',
                    'data[paymentsNum]': '0',
                    'data[allPaymentsNum]': '1',
                    'data[paymentDate]': '31/7/24',
                    'data[description]': 'Blender x 1',
                    'data[fullName]': 'Full Name',
                    'data[payerPhone]': '0000000000',
                    'data[payerEmail]': '',
                    'data[transactionId]': '100',
                    'data[transactionToken]': 'abcd',
                    'data[processToken]': 'abcd',
                },
            ),
            content_type='application/x-www-form-urlencoded',
        )
        content = json.loads(response.content.decode(encoding='UTF-8'))

        # response is always successfull
        self.assertDictEqual(
            content,
            {
                'success': True,
                'status': 200,
                'data': {},
            },
        )

        # order is still paid
        self.payment_info.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment_info.is_paid, True)
        self.assertEqual(self.order.status, Order.OrderStatusEnum.PENDING.name)

    def test_webhooke_payment_not_paid_yet(self):
        # data[statusCode] is not '2' (which means paid)
        response = self.client.post(
            self.route,
            data=urllib.parse.urlencode(
                {
                    'err': '',
                    'status': '1',
                    'data[processId]': self.payment_info.process_id,
                    'data[customFields][cField1]': 'verysecret',
                    'data[statusCode]': '1',
                    'data[asmachta]': '123',
                    'data[cardSuffix]': '0000',
                    'data[cardType]': 'Local',
                    'data[cardTypeCode]': '1',
                    'data[cardBrand]': 'Visa',
                    'data[cardBrandCode]': '3',
                    'data[cardExp]': '1224',
                    'data[firstPaymentSum]': '0',
                    'data[periodicalPaymentSum]': '0',
                    'data[status]': '\u05e9\u05d5\u05dc\u05dd',
                    'data[transactionTypeId]': '1',
                    'data[paymentType]': '2',
                    'data[sum]': '40',
                    'data[paymentsNum]': '0',
                    'data[allPaymentsNum]': '1',
                    'data[paymentDate]': '31/7/24',
                    'data[description]': 'Blender x 1',
                    'data[fullName]': 'Full Name',
                    'data[payerPhone]': '0000000000',
                    'data[payerEmail]': '',
                    'data[transactionId]': '100',
                    'data[transactionToken]': 'abcd',
                    'data[processToken]': 'abcd',
                },
            ),
            content_type='application/x-www-form-urlencoded',
        )
        content = json.loads(response.content.decode(encoding='UTF-8'))

        # response is always successfull
        self.assertDictEqual(
            content,
            {
                'success': True,
                'status': 200,
                'data': {},
            },
        )

        # order is not paid yet
        self.payment_info.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment_info.is_paid, False)
        self.assertEqual(self.order.status, Order.OrderStatusEnum.INCOMPLETE.name)

    @responses.activate
    def test_webhook_payment_paid_approve_failure(self):
        responses.add(
            responses.POST,
            f'{settings.GROW_BASE_URL}/approveTransaction',
            json={'err': 'some error', 'status': 0},
        )

        response = self.client.post(
            self.route,
            data=urllib.parse.urlencode(
                {
                    'err': '',
                    'status': '1',
                    'data[processId]': self.payment_info.process_id,
                    'data[customFields][cField1]': 'verysecret',
                    'data[statusCode]': '2',
                    'data[asmachta]': '123',
                    'data[cardSuffix]': '0000',
                    'data[cardType]': 'Local',
                    'data[cardTypeCode]': '1',
                    'data[cardBrand]': 'Visa',
                    'data[cardBrandCode]': '3',
                    'data[cardExp]': '1224',
                    'data[firstPaymentSum]': '0',
                    'data[periodicalPaymentSum]': '0',
                    'data[status]': '\u05e9\u05d5\u05dc\u05dd',
                    'data[transactionTypeId]': '1',
                    'data[paymentType]': '2',
                    'data[sum]': '40',
                    'data[paymentsNum]': '0',
                    'data[allPaymentsNum]': '1',
                    'data[paymentDate]': '31/7/24',
                    'data[description]': 'Blender x 1',
                    'data[fullName]': 'Full Name',
                    'data[payerPhone]': '0000000000',
                    'data[payerEmail]': '',
                    'data[transactionId]': '100',
                    'data[transactionToken]': 'abcd',
                    'data[processToken]': 'abcd',
                },
            ),
            content_type='application/x-www-form-urlencoded',
        )
        content = json.loads(response.content.decode(encoding='UTF-8'))

        # response is always successfull
        self.assertDictEqual(
            content,
            {
                'success': True,
                'status': 200,
                'data': {},
            },
        )

        # order is not paid yet
        self.payment_info.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment_info.is_paid, False)
        self.assertEqual(self.order.status, Order.OrderStatusEnum.INCOMPLETE.name)

    @responses.activate
    def test_webhook_payment_paid_approve_success(self):
        responses.add(
            responses.POST,
            f'{settings.GROW_BASE_URL}/approveTransaction',
            json={'err': '', 'status': 1},
        )

        response = self.client.post(
            self.route,
            data=urllib.parse.urlencode(
                {
                    'err': '',
                    'status': '1',
                    'data[processId]': self.payment_info.process_id,
                    'data[customFields][cField1]': 'verysecret',
                    'data[statusCode]': '2',
                    'data[asmachta]': '123',
                    'data[cardSuffix]': '0000',
                    'data[cardType]': 'Local',
                    'data[cardTypeCode]': '1',
                    'data[cardBrand]': 'Visa',
                    'data[cardBrandCode]': '3',
                    'data[cardExp]': '1224',
                    'data[firstPaymentSum]': '0',
                    'data[periodicalPaymentSum]': '0',
                    'data[status]': '\u05e9\u05d5\u05dc\u05dd',
                    'data[transactionTypeId]': '1',
                    'data[paymentType]': '2',
                    'data[sum]': '40',
                    'data[paymentsNum]': '0',
                    'data[allPaymentsNum]': '1',
                    'data[paymentDate]': '31/7/24',
                    'data[description]': 'Blender x 1',
                    'data[fullName]': 'Full Name',
                    'data[payerPhone]': '0000000000',
                    'data[payerEmail]': '',
                    'data[transactionId]': '100',
                    'data[transactionToken]': 'abcd',
                    'data[processToken]': 'abcd',
                },
            ),
            content_type='application/x-www-form-urlencoded',
        )
        content = json.loads(response.content.decode(encoding='UTF-8'))

        # response is always successfull
        self.assertDictEqual(
            content,
            {
                'success': True,
                'status': 200,
                'data': {},
            },
        )

        # order is was paid!
        self.payment_info.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment_info.is_paid, True)
        self.assertEqual(self.order.status, Order.OrderStatusEnum.PENDING.name)
