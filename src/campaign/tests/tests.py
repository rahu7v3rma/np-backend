from datetime import datetime, timedelta, timezone
import json
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import (
    Q,
)
from django.test import TestCase
from django.utils import timezone as django_timezone
from rest_framework import status
from rest_framework.test import APIClient

from campaign.models import (
    Campaign,
    CampaignEmployee,
    Cart,
    CartProduct,
    DeliveryLocationEnum,
    Employee,
    EmployeeAuthEnum,
    EmployeeGroup,
    EmployeeGroupCampaign,
    EmployeeGroupCampaignProduct,
    Order,
    OrderProduct,
    Organization,
    OrganizationProduct,
    QuickOffer,
    QuickOfferOrder,
    QuickOfferOrderProduct,
    QuickOfferSelectedProduct,
)
from campaign.serializers import (
    QuickOfferProductSerializer,
    QuickOfferSelectProductsDetailSerializer,
    QuickOfferSerializer,
)
from inventory.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    Share,
    ShareTypeEnum,
    Supplier,
    Tag,
)
from services.auth import jwt_encode
from src.campaign.serializers import QuickOfferReadOnlySerializer


User = get_user_model()


class CampaignViewTestCase(TestCase):
    def setUp(self):
        self.route = '/campaign/{}/details'
        self.client = APIClient()

        self.organization = Organization.objects.create(
            name='name en',
            name_he='name he',
            manager_full_name='test',
            manager_phone_number='086786',
            manager_email='info@gmail.com',
        )
        self.employee_group = EmployeeGroup.objects.create(
            name='test employee',
            organization=self.organization,
            auth_method='AUTH_ID',
            delivery_location='ToHome',
        )
        self.user = User.objects.create(
            email='user@domain.com',
            username='user_username',
            password='user_password',
        )
        self.employee = Employee.objects.create(
            first_name='employee_first_name',
            last_name='employee_last_name',
            first_name_he='employee_first_name_he',
            last_name_he='employee_last_name_he',
            auth_id='employee_auth_id',
            active=True,
            email='user@domain.com',
            employee_group=EmployeeGroup.objects.first(),
        )
        self.employee_2 = Employee.objects.create(
            first_name='employee_first_name_2',
            last_name='employee_last_name_2',
            auth_id='employee_auth_id_2',
            active=True,
            email='user2@domain.com',
            employee_group=EmployeeGroup.objects.first(),
        )
        self.campaign = Campaign.objects.create(
            organization=self.organization,
            name='campaign name',
            name_he='campaign name he',
            start_date_time=django_timezone.now(),
            end_date_time=django_timezone.now() + django_timezone.timedelta(hours=1),
            status='ACTIVE',
            login_page_title='en',
            login_page_title_he='he',
            login_page_subtitle='en',
            login_page_subtitle_he='he',
            main_page_first_banner_title='en',
            main_page_first_banner_title_he='he',
            main_page_first_banner_subtitle='en',
            main_page_first_banner_subtitle_he='he',
            main_page_first_banner_image='image',
            main_page_first_banner_mobile_image='mobile_image',
            main_page_second_banner_title='en',
            main_page_second_banner_title_he='he',
            main_page_second_banner_subtitle='en',
            main_page_second_banner_subtitle_he='he',
            main_page_second_banner_background_color='#123456',
            main_page_second_banner_text_color='WHITE',
            sms_sender_name='sender',
            sms_welcome_text='en',
            sms_welcome_text_he='he',
            email_welcome_text='en',
            email_welcome_text_he='he',
        )
        self.employee_group_campaign = EmployeeGroupCampaign.objects.create(
            campaign=self.campaign,
            employee_group=self.employee_group,
            budget_per_employee=3000,
            product_selection_mode=EmployeeGroupCampaign.ProductSelectionTypeEnum.MULTIPLE.value,
            displayed_currency=EmployeeGroupCampaign.CurrencyTypeEnum.CURRENCY.value,
            check_out_location=EmployeeGroupCampaign.CheckoutLocationTypeEnum.ISRAEL.value,
        )
        self.campaign_employee = CampaignEmployee.objects.create(
            campaign=self.campaign, employee=self.employee
        )
        self.campaign_employee_2 = CampaignEmployee.objects.create(
            campaign=self.campaign, employee=self.employee_2
        )

        self.campaign_2 = Campaign.objects.create(
            organization=self.organization,
            name='second campaign name',
            name_he='secpnd campaign name he',
            start_date_time=django_timezone.now(),
            end_date_time=django_timezone.now() + django_timezone.timedelta(hours=1),
            status='ACTIVE',
            login_page_title='en',
            login_page_title_he='he',
            login_page_subtitle='en',
            login_page_subtitle_he='he',
            main_page_first_banner_title='en',
            main_page_first_banner_title_he='he',
            main_page_first_banner_subtitle='en',
            main_page_first_banner_subtitle_he='he',
            main_page_first_banner_image='image',
            main_page_first_banner_mobile_image='mobile_image',
            main_page_second_banner_title='en',
            main_page_second_banner_title_he='he',
            main_page_second_banner_subtitle='en',
            main_page_second_banner_subtitle_he='he',
            main_page_second_banner_background_color='#123456',
            main_page_second_banner_text_color='WHITE',
            sms_sender_name='sender',
            sms_welcome_text='en',
            sms_welcome_text_he='he',
            email_welcome_text='en',
            email_welcome_text_he='he',
        )
        EmployeeGroupCampaign.objects.create(
            campaign=self.campaign_2,
            employee_group=self.employee_group,
            budget_per_employee=3000,
            product_selection_mode=EmployeeGroupCampaign.ProductSelectionTypeEnum.MULTIPLE.value,
            displayed_currency=EmployeeGroupCampaign.CurrencyTypeEnum.CURRENCY.value,
            check_out_location=EmployeeGroupCampaign.CheckoutLocationTypeEnum.ISRAEL.value,
        )
        self.campaign_2_employee = CampaignEmployee.objects.create(
            campaign=self.campaign_2, employee=self.employee
        )

        self.campaign.refresh_from_db()
        self.code = self.campaign.code
        self.code_2 = self.campaign_2.code

    def test_request_code_not_found(self):
        response = self.client.get(self.route.format('123456'))
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Campaign does not exist.',
                'code': 'not_found',
                'status': 404,
                'data': {},
            },
        )

    def test_request_valid_code_non_employee(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        # should get normal campaign details like a non-authorized request
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'Campaign fetched successfully.',
                'status': 200,
                'data': {
                    'name': 'campaign name',
                    'code': self.code,
                    'is_active': True,
                    'organization_name': 'name en',
                    'organization_logo_image': None,
                    'login_page_title': 'en',
                    'login_page_subtitle': 'en',
                    'login_page_image': None,
                    'login_page_mobile_image': None,
                },
            },
        )

    def test_request_valid_code_employee(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        # should get extended campaign details
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'Campaign fetched successfully.',
                'status': 200,
                'data': {
                    'name': 'campaign name',
                    'code': self.code,
                    'is_active': True,
                    'organization_name': 'name en',
                    'organization_logo_image': None,
                    'login_page_title': 'en',
                    'login_page_subtitle': 'en',
                    'login_page_image': None,
                    'login_page_mobile_image': None,
                    'main_page_first_banner_title': 'en',
                    'main_page_first_banner_subtitle': 'en',
                    'main_page_first_banner_image': '/media/image',
                    'main_page_first_banner_mobile_image': '/media/mobile_image',
                    'main_page_second_banner_title': 'en',
                    'main_page_second_banner_subtitle': 'en',
                    'main_page_second_banner_background_color': '#123456',
                    'main_page_second_banner_text_color': 'WHITE',
                    'delivery_location': 'ToHome',
                    'office_delivery_address': None,
                    'product_selection_mode': 'Multiple',
                    'displayed_currency': 'Currency',
                    'budget_per_employee': 3000,
                    'employee_order_reference': None,
                    'employee_name': 'employee_first_name employee_last_name',
                    'check_out_location': 'Israel',
                },
            },
        )

    def test_request_unuathorized_code_lang(self):
        response = self.client.get(f'{self.route.format(self.code)}?lang=he')
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'Campaign fetched successfully.',
                'status': 200,
                'data': {
                    'name': 'campaign name he',
                    'code': self.code,
                    'is_active': True,
                    'organization_name': 'name he',
                    'organization_logo_image': None,
                    'login_page_title': 'he',
                    'login_page_subtitle': 'he',
                    'login_page_image': None,
                    'login_page_mobile_image': None,
                },
            },
        )

    def test_request_valid_code_lang(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(f'{self.route.format(self.code)}?lang=he')
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'Campaign fetched successfully.',
                'status': 200,
                'data': {
                    'name': 'campaign name he',
                    'code': self.code,
                    'is_active': True,
                    'organization_name': 'name he',
                    'organization_logo_image': None,
                    'login_page_title': 'he',
                    'login_page_subtitle': 'he',
                    'login_page_image': None,
                    'login_page_mobile_image': None,
                    'main_page_first_banner_title': 'he',
                    'main_page_first_banner_subtitle': 'he',
                    'main_page_first_banner_image': '/media/image',
                    'main_page_first_banner_mobile_image': '/media/mobile_image',
                    'main_page_second_banner_title': 'he',
                    'main_page_second_banner_subtitle': 'he',
                    'main_page_second_banner_background_color': '#123456',
                    'main_page_second_banner_text_color': 'WHITE',
                    'delivery_location': 'ToHome',
                    'office_delivery_address': None,
                    'product_selection_mode': 'Multiple',
                    'displayed_currency': 'Currency',
                    'budget_per_employee': 3000,
                    'employee_order_reference': None,
                    'employee_name': 'employee_first_name_he employee_last_name_he',
                    'check_out_location': 'Israel',
                },
            },
        )

    def test_request_invalid_code_lang(self):
        response = self.client.get(f'{self.route.format(self.code)}?lang=invalid')
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {
                    'lang': [
                        'Provided choice is invalid. '
                        "Available choices are: ('en', 'he')"
                    ]
                },
            },
        )

    def test_request_employee_delivery_fields(self):
        self.client.force_authenticate(user=self.employee)

        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['delivery_location'], 'ToHome')
        self.assertEqual(response.json()['data']['office_delivery_address'], None)

        # update employee group delivery address
        self.employee_group.delivery_city = 'city'
        self.employee_group.delivery_street = 'street'
        self.employee_group.delivery_street_number = '1'
        self.employee_group.delivery_apartment_number = '123'
        self.employee_group.save()
        self.employee_group.refresh_from_db()
        self.employee.refresh_from_db()

        # there should still be no office_delivery_address value since the
        # delivery location is set to ToHome
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['delivery_location'], 'ToHome')
        self.assertEqual(response.json()['data']['office_delivery_address'], None)

        # update employee group delivery location
        self.employee_group.delivery_location = DeliveryLocationEnum.ToOffice.name
        self.employee_group.save()
        self.employee_group.refresh_from_db()
        self.employee.refresh_from_db()

        # both values should be provided now
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['delivery_location'], 'ToOffice')
        self.assertEqual(
            response.json()['data']['office_delivery_address'],
            'street 1, 123, city',
        )

    def test_request_employee_order_reference(self):
        self.client.force_authenticate(user=self.employee)

        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['employee_order_reference'], None)

        # create an order for another employee
        Order.objects.create(
            campaign_employee_id=self.campaign_employee_2,
            order_date_time=datetime.now(timezone.utc),
            cost_from_budget=50,
            cost_added=0,
        )
        self.employee.refresh_from_db()

        # employee's order reference should still be none
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['employee_order_reference'], None)

        # create an order for the current employee
        employee_order = Order.objects.create(
            campaign_employee_id=self.campaign_employee,
            order_date_time=datetime.now(timezone.utc),
            cost_from_budget=50,
            cost_added=0,
        )
        self.employee.refresh_from_db()

        # employee's order reference should still be none because the order
        # status is incomplete by default
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['employee_order_reference'], None)

        # update order status to pending
        employee_order.status = Order.OrderStatusEnum.PENDING.name
        employee_order.save()
        self.employee.refresh_from_db()

        # employee's order reference should now be returned
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['data']['employee_order_reference'],
            employee_order.reference,
        )

        # update order status to cancelled
        employee_order.status = Order.OrderStatusEnum.CANCELLED.name
        employee_order.save()
        self.employee.refresh_from_db()

        # employee's order reference should again not be returned
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['employee_order_reference'], None)

    def test_request_employee_other_campaign_order_reference(self):
        self.client.force_authenticate(user=self.employee)

        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['employee_order_reference'], None)

        # create a pending order for the employee
        employee_order = Order.objects.create(
            campaign_employee_id=self.campaign_employee,
            order_date_time=datetime.now(timezone.utc),
            cost_from_budget=50,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
        )
        self.employee.refresh_from_db()

        # employee's order reference should be returned when working with the
        # first campaign
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['data']['employee_order_reference'],
            employee_order.reference,
        )

        # employee's order reference should not be returned when working with
        # the second campaign
        response = self.client.get(self.route.format(self.code_2))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['employee_order_reference'], None)

        # create a pending order for the second campaign
        employee_order_2 = Order.objects.create(
            campaign_employee_id=self.campaign_2_employee,
            order_date_time=datetime.now(timezone.utc),
            cost_from_budget=50,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
        )
        self.employee.refresh_from_db()

        # the employee's order from the second campaign should now be returned
        response = self.client.get(self.route.format(self.code_2))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['data']['employee_order_reference'],
            employee_order_2.reference,
        )

        # but the first campaign's order will still be returned when working
        # with the first campaign
        response = self.client.get(self.route.format(self.code))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['data']['employee_order_reference'],
            employee_order.reference,
        )


class CampaignCategoriesViewTestCase(TestCase):
    def setUp(self):
        self.route = '/campaign/{}/categories'
        self.client = APIClient()

        self.organization = Organization.objects.create(
            name='Test',
            manager_full_name='test',
            manager_phone_number='086786',
            manager_email='info@gmail.com',
        )
        self.employee_group = EmployeeGroup.objects.create(
            name='test employee',
            organization=self.organization,
            auth_method='AUTH_ID',
        )
        self.campaign = Campaign.objects.create(
            organization=self.organization,
            name='campaign name',
            name_he='campaign name he',
            start_date_time=datetime.now(),
            end_date_time=datetime.now() + timedelta(hours=1),
            status='ACTIVE',
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
        self.employee = Employee.objects.create(
            first_name='employee_first_name',
            last_name='employee_last_name',
            auth_id='employee_auth_id',
            active=True,
            employee_group=self.employee_group,
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
        self.organization.products.add(self.product, through_defaults={'price': 3000})

        self.employee_group_campaign = EmployeeGroupCampaign.objects.create(
            campaign=self.campaign,
            employee_group=self.employee_group,
            budget_per_employee=3000,
        )
        EmployeeGroupCampaignProduct.objects.create(
            employee_group_campaign_id=self.employee_group_campaign,
            product_id=self.product,
        )
        self.employee_group.campaigns.add(
            self.campaign,
            through_defaults={
                'budget_per_employee': self.employee_group_campaign.budget_per_employee
            },
        )

        self.employee_group_campaign_product = (
            EmployeeGroupCampaignProduct.objects.create(
                employee_group_campaign_id=self.employee_group_campaign,
                product_id=self.product,
            ),
        )

        CampaignEmployee.objects.create(campaign=self.campaign, employee=self.employee)

    def test_fetch_campaign_categories_successfully(self):
        auth_response = self.client.post(
            f'/campaign/{self.campaign.code}/login',
            format='json',
            data={
                'auth_id': self.employee.auth_id,
            },
        )
        self.assertEqual(auth_response.status_code, 200)
        auth_content = json.loads(auth_response.content.decode(encoding='UTF-8'))
        employee_token = auth_content['data']['auth_token']

        self.client.credentials(HTTP_X_AUTHORIZATION=f'Bearer {employee_token}')
        response = self.client.get(f'/campaign/{self.campaign.code}/categories?lang=en')
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'Categories fetched successfully.',
                'code': 'categories_fetched',
                'status': 200,
                'data': {
                    'categories': [
                        {
                            'id': 1,
                            'name': 'nicklas',
                            'icon_image': '/media/test.jpg',
                            'order': 0,
                        },
                        {
                            'id': 2,
                            'name': 'category2 en',
                            'icon_image': '/media/icon2.jpg',
                            'order': 0,
                        },
                    ]
                },
            },
        )

    def test_fetch_campaign_categories_by_wrong_compaign_code(self):
        auth_response = self.client.post(
            f'/campaign/{self.campaign.code}/login',
            format='json',
            data={
                'auth_id': self.employee.auth_id,
            },
        )
        self.assertEqual(auth_response.status_code, 200)
        auth_content = json.loads(auth_response.content.decode(encoding='UTF-8'))
        employee_token = auth_content['data']['auth_token']

        self.client.credentials(HTTP_X_AUTHORIZATION=f'Bearer {employee_token}')
        response = self.client.get('/campaign/12/categories')
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Campaign not found.',
                'code': 'campaign_not_found',
                'status': 404,
            },
        )

    def test_fetch_campaign_categories_by_inactive_compaign(self):
        auth_response = self.client.post(
            f'/campaign/{self.campaign.code}/login',
            format='json',
            data={
                'auth_id': self.employee.auth_id,
            },
        )
        self.assertEqual(auth_response.status_code, 200)
        auth_content = json.loads(auth_response.content.decode(encoding='UTF-8'))
        employee_token = auth_content['data']['auth_token']

        self.client.credentials(HTTP_X_AUTHORIZATION=f'Bearer {employee_token}')
        self.campaign.status = 'PENDING'
        self.campaign.save()
        self.campaign.refresh_from_db()
        response = self.client.get(f'/campaign/{self.campaign.code}/categories')
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Campaign not found.',
                'code': 'campaign_not_found',
                'status': 404,
            },
        )

    def test_fetch_campaign_categories_without_authentication(self):
        response = self.client.get(f'/campaign/{self.campaign.code}/categories')
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_invalid_lang(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            f'/campaign/{self.campaign.code}/categories?lang=invalid'
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {
                    'lang': [
                        'Provided choice is invalid. '
                        "Available choices are: ('en', 'he')"
                    ]
                },
            },
        )


class ProductViewTestCase(TestCase):
    fixtures = ['src/fixtures/products.json']

    def setUp(self):
        self.route = '/campaign/{}/product/{}/details/'
        self.client = APIClient()
        self.employee = Employee.objects.create(
            first_name='employee_first_name',
            last_name='employee_last_name',
            auth_id='employee_auth_id',
            active=True,
            employee_group=EmployeeGroup.objects.first(),
        )

    def test_request_without_auth(self):
        response = self.client.get(self.route.format('123456', '1'))
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_request_wrong_product_id(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '12')
        )
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Product does not exist.',
        )

    def test_request_wrong_campaign_id(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format(Campaign.objects.last().code, '1'))
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Product does not exist.',
        )

    def test_request_inactive_campaign(self):
        self.client.force_authenticate(user=self.employee)
        campaign = Campaign.objects.first()
        campaign.status = 'PENDING'
        campaign.save()
        campaign.refresh_from_db()
        response = self.client.get(self.route.format(campaign.code, '1'))
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Product does not exist.',
        )

    def test_request_correct_product_id_campaign_code_lang(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1') + '?lang=en'
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'Product data fetched successfully.',
                'status': 200,
                'data': {
                    'id': 1,
                    'name': 'product1',
                    'description': 'desc',
                    'sku': '1234',
                    'link': '',
                    'technical_details': '',
                    'warranty': '',
                    'exchange_value': None,
                    'exchange_policy': '',
                    'product_type': 'REGULAR',
                    'product_kind': 'PHYSICAL',
                    'brand': {'name': 'brand1', 'logo_image': None},
                    'supplier': {
                        'name': 'supplier1',
                    },
                    'images': [
                        {
                            'main': True,
                            'image': '/media/934282de-6c0c-4209-b1aa-bd1a8f0f7c0a.jpeg',
                        }
                    ],
                    'categories': [
                        {'id': 1, 'name': 'cat1', 'icon_image': None, 'order': 0}
                    ],
                    'calculated_price': 14,
                    'extra_price': 5,
                    'remaining_quantity': 2147483647,
                },
            },
        )

    def test_request_correct_product_id_campaign_code_he(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            f"{self.route.format(Campaign.objects.first().code, '1')}?lang=he"
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(content.get('data').get('name'), 'product1 he')
        self.assertEqual(
            content.get('data').get('brand').get('name'),
            'brand1 he',
        )
        self.assertEqual(
            content.get('data').get('supplier').get('name'),
            'supplier1 he',
        )
        self.assertEqual(
            content.get('data').get('categories')[0].get('name'),
            'cat1 he',
        )

    def test_invalid_lang(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1') + '?lang=invalid'
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {
                    'lang': [
                        'Provided choice is invalid. '
                        "Available choices are: ('en', 'he')"
                    ]
                },
            },
        )

    def test_request_cost_with_multiple_employee_group_budgets(self):
        # create a second employee group with a higher budget
        second_employee_group = EmployeeGroup.objects.create(
            name='second employee group',
            organization=Organization.objects.get(pk=1),
            auth_method='AUTH_ID',
        )
        second_employee_group_campaign = EmployeeGroupCampaign.objects.create(
            employee_group=second_employee_group,
            campaign=Campaign.objects.get(pk=1),
            budget_per_employee=20,
        )
        EmployeeGroupCampaignProduct.objects.create(
            employee_group_campaign_id=second_employee_group_campaign,
            product_id=Product.objects.get(pk=1),
        )
        second_employee = Employee.objects.create(
            first_name='second_employee_first_name',
            last_name='second_employee_last_name',
            auth_id='secod_employee_auth_id',
            active=True,
            employee_group=second_employee_group,
        )

        # authenticate with the second employee who has a different budget
        self.client.force_authenticate(user=second_employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1')
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))

        # make sure extra cost is still calculated based on the authorized
        # user's employee group's budget and not any other group's budget
        self.assertEqual(content.get('data').get('calculated_price'), 14)
        self.assertEqual(content.get('data').get('extra_price'), 0)


class CampaignProductViewTestCase(TestCase):
    fixtures = ['src/fixtures/products.json']

    def setUp(self):
        self.route = '/campaign/{}/products/'
        self.client = APIClient()
        self.employee = Employee.objects.create(
            first_name='employee_first_name',
            last_name='employee_last_name',
            auth_id='employee_auth_id',
            active=True,
            employee_group=EmployeeGroup.objects.first(),
        )
        self.campaign = Campaign.objects.first()
        product = Product.objects.first()
        self.employee_group_campaign = EmployeeGroupCampaign.objects.first()
        self.employee_group_campaign.budget_per_employee = 105
        self.employee_group_campaign.save()

        for i in range(10):
            tmp_product = product
            tmp_product.id = None
            tmp_product.sku = f'12345{str(i)}'
            tmp_product.cost_price = 100 + i
            tmp_product.save()
            EmployeeGroupCampaignProduct.objects.create(
                employee_group_campaign_id=self.employee_group_campaign,
                product_id=tmp_product,
            )

    def test_request_without_auth(self):
        response = self.client.get(self.route.format(Campaign.objects.first().code))
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_request_wrong_campaign_code(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format('0123456789012345'))
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Campaign not found.',
        )

    def test_request_inactive_campaign(self):
        self.client.force_authenticate(user=self.employee)
        campaign = Campaign.objects.first()
        campaign.status = 'PENDING'
        campaign.save()
        campaign.refresh_from_db()
        response = self.client.get(self.route.format(campaign.code, '1'))
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Campaign not found.',
        )

    def test_request_correct_campaign_code_lang(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1') + '?lang=en'
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(content['status'], status.HTTP_200_OK)

    def test_request_pagination(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1') + '?page=1&limit=3'
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertListEqual(
            list(map(lambda x: x.get('id'), content.get('data').get('page_data'))),
            [1, 2, 3],
        )

        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1') + '?page=2&limit=4'
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertListEqual(
            list(map(lambda x: x.get('id'), content.get('data').get('page_data'))),
            [5, 6, 7, 8],
        )

        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1') + '?page=2&limit=10'
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertListEqual(
            list(map(lambda x: x.get('id'), content.get('data').get('page_data'))), [11]
        )

    def test_request_category(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1')
            + '?page=1&limit=3&category_id=1'
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertListEqual(
            list(map(lambda x: x.get('id'), content.get('data').get('page_data'))),
            [1],
        )

        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1')
            + '?page=1&limit=3&category_id=2'
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertListEqual(
            list(map(lambda x: x.get('id'), content.get('data').get('page_data'))), []
        )

    def test_request_search(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1')
            + '?page=1&limit=3&q=prod'
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertListEqual(
            list(map(lambda x: x.get('id'), content.get('data').get('page_data'))),
            [1, 2, 3],
        )

        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1')
            + '?page=1&limit=3&q=prod_not_exists'
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertListEqual(
            list(map(lambda x: x.get('id'), content.get('data').get('page_data'))), []
        )

    def test_invalid_lang_query_param(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1') + '?lang=invalid'
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {
                    'lang': [
                        'Provided choice is invalid. '
                        "Available choices are: ('en', 'he')"
                    ]
                },
            },
        )

    def test_original_budget_zero(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1') + '?original_budget=0'
        )
        response_products = [
            product.get('id')
            for product in response.json().get('data', {}).get('page_data')
        ]
        expected_products = EmployeeGroupCampaignProduct.objects.filter(
            employee_group_campaign_id=self.employee_group_campaign,
        )[:10].values_list('id', flat=True)
        self.assertEqual(sorted(response_products), sorted(list(expected_products)))

    def test_original_budget_one(self):
        p = self.create_products()
        p[0]['organization_product'].price = 105
        p[0]['organization_product'].save()
        p[0]['product'].sale_price = 0
        p[0]['product'].save()
        p[1]['organization_product'].price = 0
        p[1]['organization_product'].save()
        p[1]['product'].sale_price = 105
        p[1]['product'].save()
        expected_response_products_ids = [
            p[1]['employee_group_campaign_product'].pk,
            p[0]['employee_group_campaign_product'].pk,
        ]
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(
            self.route.format(Campaign.objects.first().code, '1') + '?original_budget=1'
        )
        response_products = [
            product.get('id')
            for product in response.json().get('data', {}).get('page_data')
        ]
        self.assertEqual(
            sorted(response_products), sorted(list(expected_response_products_ids))
        )

    def create_products(self):
        Product.objects.all().delete()
        OrganizationProduct.objects.all().delete()
        EmployeeGroupCampaignProduct.objects.all().delete()
        results = []
        for i in range(2):
            product = Product.objects.create(
                brand=Brand.objects.first(),
                supplier=Supplier.objects.first(),
                sale_price=0,
                name='name',
                product_kind='physical',
                product_type='regular',
                description='description',
                sku=f'sku_{i}',
                cost_price=100,
            )
            organization_product = OrganizationProduct.objects.create(
                organization=self.campaign.organization,
                product=product,
                price=0,
            )
            employee_group_campaign_product = (
                EmployeeGroupCampaignProduct.objects.create(
                    employee_group_campaign_id=EmployeeGroupCampaign.objects.filter(
                        employee_group=self.employee.employee_group,
                        campaign=self.campaign,
                    ).first(),
                    product_id=product,
                )
            )
            results.append(
                {
                    'product': product,
                    'organization_product': organization_product,
                    'employee_group_campaign_product': employee_group_campaign_product,
                }
            )
        return results

    def test_sort_by_organization_product_price(self):
        p = self.create_products()
        p[0]['organization_product'].price = 100
        p[0]['organization_product'].save()
        p[0]['product'].sale_price = 0
        p[0]['product'].save()
        p[1]['organization_product'].price = 90
        p[1]['organization_product'].save()
        p[1]['product'].sale_price = 0
        p[1]['product'].save()
        expected_response_products_ids = [
            p[1]['employee_group_campaign_product'].pk,
            p[0]['employee_group_campaign_product'].pk,
        ]
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format(self.campaign.code))
        response_products_ids = [
            product.get('id')
            for product in response.json().get('data', {}).get('page_data')
        ]
        self.assertEqual(response_products_ids, expected_response_products_ids)

    def test_sort_by_sale_price(self):
        p = self.create_products()
        p[0]['organization_product'].price = 0
        p[0]['organization_product'].save()
        p[0]['product'].sale_price = 100
        p[0]['product'].save()
        p[1]['organization_product'].price = 0
        p[1]['organization_product'].save()
        p[1]['product'].sale_price = 90
        p[1]['product'].save()
        expected_response_products_ids = [
            p[1]['employee_group_campaign_product'].pk,
            p[0]['employee_group_campaign_product'].pk,
        ]
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format(self.campaign.code))
        response_products_ids = [
            product.get('id')
            for product in response.json().get('data', {}).get('page_data')
        ]
        self.assertEqual(response_products_ids, expected_response_products_ids)

    def test_sort_by_both_organization_product_price_and_sale_price(self):
        p = self.create_products()
        p[0]['organization_product'].price = 100
        p[0]['organization_product'].save()
        p[0]['product'].sale_price = 0
        p[0]['product'].save()
        p[1]['organization_product'].price = 0
        p[1]['organization_product'].save()
        p[1]['product'].sale_price = 110
        p[1]['product'].save()
        expected_response_products_ids = [
            p[0]['employee_group_campaign_product'].pk,
            p[1]['employee_group_campaign_product'].pk,
        ]
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format(self.campaign.code))
        response_products_ids = [
            product.get('id')
            for product in response.json().get('data', {}).get('page_data')
        ]
        self.assertEqual(response_products_ids, expected_response_products_ids)


class EmployeeLoginView(TestCase):
    def setUp(self):
        self.route = '/campaign/{campaign_code}/login'
        self.client = APIClient()
        self.employee_group1 = EmployeeGroup.objects.create(
            name='employee_group1',
            auth_method=EmployeeAuthEnum.SMS.name,
        )
        self.employee_group2 = EmployeeGroup.objects.create(name='employee_group2')
        self.employee1 = Employee.objects.create(
            first_name='employee1',
            last_name='employee1',
            auth_id='employee1',
            active=True,
            email='employee1@domain.com',
            phone_number='0500000000',
            employee_group=self.employee_group1,
        )
        self.employee2 = Employee.objects.create(
            first_name='employee2',
            last_name='employee2',
            auth_id='employee2',
            active=True,
            email='employee2@domain.com',
            phone_number='0500000001',
            employee_group=self.employee_group2,
        )
        self.organization1 = Organization.objects.create(
            name='organization1',
            manager_full_name='organization1',
            manager_phone_number='0525252525',
            manager_email='organization1',
        )

        self.organization2 = Organization.objects.create(
            name='organization2',
            manager_full_name='organization2',
            manager_phone_number='0525252525',
            manager_email='organization2',
        )
        self.campaign1 = Campaign.objects.create(
            organization=self.organization1,
            name='campaign1',
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
        self.campaign1.employees.add(self.employee1)
        self.campaign1.save()
        self.campaign2 = Campaign.objects.create(
            organization=self.organization2,
            name='campaign2',
            start_date_time=datetime.now(timezone.utc) + timedelta(days=1),
            end_date_time=datetime.now(timezone.utc) + timedelta(days=10),
            status=Campaign.CampaignStatusEnum.PENDING.name,
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
        self.campaign2.employees.add(self.employee2)
        self.campaign2.save()

        self.egc1 = EmployeeGroupCampaign.objects.create(
            campaign=self.campaign1,
            employee_group=self.employee_group1,
            budget_per_employee=1,
        )
        self.egc2 = EmployeeGroupCampaign.objects.create(
            campaign=self.campaign2,
            employee_group=self.employee_group2,
            budget_per_employee=2,
        )

    def tearDown(self):
        del self.route
        del self.client
        Employee.objects.all().delete()
        Campaign.objects.all().delete()
        EmployeeGroup.objects.all().delete()
        Organization.objects.all().delete()
        EmployeeGroupCampaign.objects.all().delete()

    def test_campaign_not_found(self):
        response = self.client.post(self.route.replace('{campaign_code}', '0'))
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_campaign_inactive(self):
        self.campaign1.status = Campaign.CampaignStatusEnum.FINISHED.name
        self.campaign1.save()
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code)
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_without_request_body(self):
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code)
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {
                    'non_field_errors': [
                        'Either email, phone_number or auth_id must be provided'
                    ]
                },
            },
        )

    def test_employee_not_found(self):
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'email': 'invalid@employee.com',
            },
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_employee_not_related_to_campaign(self):
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'phone_number': self.employee2.phone_number,
            },
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_employee_inactive(self):
        self.employee1.active = False
        self.employee1.save()
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'phone_number': self.employee1.phone_number,
            },
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_employee_group_campaign_not_found(self):
        EmployeeGroupCampaign.objects.get(campaign=self.campaign1).delete()
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'phone_number': self.employee1.phone_number,
            },
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_egc_auth_method_mismatch_request_body(self):
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'email': self.employee1.email,
            },
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_auth_id(self):
        self.employee_group1.auth_method = 'AUTH_ID'
        self.employee_group1.save()
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'auth_id': self.employee1.auth_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'User logged in successfully',
                'status': 200,
                'data': {
                    'first_name': self.employee1.first_name,
                    'last_name': self.employee1.last_name,
                    'email': self.employee1.email,
                    'auth_token': jwt_encode({'employee_id': self.employee1.pk}),
                },
            },
        )

    @mock.patch('campaign.views.send_otp_token_email')
    def test_email(self, mock_send_otp_token_email):
        self.employee_group1.auth_method = 'EMAIL'
        self.employee_group1.save()
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'email': self.employee1.email,
            },
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'code': 'missing_otp',
                'message': 'Missing OTP code',
                'status': 401,
                'data': {},
            },
        )
        mock_send_otp_token_email.assert_called()
        _, kwargs = mock_send_otp_token_email.call_args
        self.employee1.refresh_from_db()
        self.assertEqual(kwargs['email'], self.employee1.email)
        otp = kwargs['otp_token']
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={'email': self.employee1.email, 'otp': otp},
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'User logged in successfully',
                'status': 200,
                'data': {
                    'first_name': self.employee1.first_name,
                    'last_name': self.employee1.last_name,
                    'email': self.employee1.email,
                    'auth_token': jwt_encode({'employee_id': self.employee1.pk}),
                },
            },
        )

    def test_invalid_phone_number(self):
        self.employee_group1.auth_method = 'SMS'
        self.employee_group1.save()
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'phone_number': 'invalid',
            },
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {'phone_number': ['Invalid phone number']},
            },
        )

    @mock.patch('campaign.views.send_otp_token_sms')
    def test_phone_number_short_form(self, mock_send_otp_token_sms):
        self.employee_group1.auth_method = 'SMS'
        self.employee_group1.save()
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'phone_number': '0500000000',
            },
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'code': 'missing_otp',
                'message': 'Missing OTP code',
                'status': 401,
                'data': {},
            },
        )
        mock_send_otp_token_sms.assert_called()
        _, kwargs = mock_send_otp_token_sms.call_args
        self.employee1.refresh_from_db()
        self.assertEqual(kwargs['phone_number'], self.employee1.phone_number)
        otp = kwargs['otp_token']
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={'phone_number': self.employee1.phone_number, 'otp': otp},
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'User logged in successfully',
                'status': 200,
                'data': {
                    'first_name': self.employee1.first_name,
                    'last_name': self.employee1.last_name,
                    'email': self.employee1.email,
                    'auth_token': jwt_encode({'employee_id': self.employee1.pk}),
                },
            },
        )

    @mock.patch('campaign.views.send_otp_token_sms')
    def test_phone_number_long_form(self, mock_send_otp_token_sms):
        self.employee_group1.auth_method = 'SMS'
        self.employee_group1.save()
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={
                'phone_number': '+972500000000',
            },
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'code': 'missing_otp',
                'message': 'Missing OTP code',
                'status': 401,
                'data': {},
            },
        )
        mock_send_otp_token_sms.assert_called()
        _, kwargs = mock_send_otp_token_sms.call_args
        self.employee1.refresh_from_db()
        self.assertEqual(kwargs['phone_number'], self.employee1.phone_number)
        otp = kwargs['otp_token']
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={'phone_number': self.employee1.phone_number, 'otp': otp},
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'User logged in successfully',
                'status': 200,
                'data': {
                    'first_name': self.employee1.first_name,
                    'last_name': self.employee1.last_name,
                    'email': self.employee1.email,
                    'auth_token': jwt_encode({'employee_id': self.employee1.pk}),
                },
            },
        )

    def test_invalid_otp(self):
        response = self.client.post(
            self.route.replace('{campaign_code}', self.campaign1.code),
            format='json',
            data={'phone_number': self.employee1.phone_number, 'otp': '00000'},
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'code': 'bad_otp',
                'message': 'Bad OTP code',
                'status': 401,
                'data': {},
            },
        )


class OrderDetailsViewTestCase(TestCase):
    fixtures = ['src/fixtures/cart_orders.json']

    def setUp(self):
        self.route = '/campaign/{}/order/details'
        self.client = APIClient()
        self.employee = Employee.objects.first()
        self.employee2 = Employee.objects.all()[1]

    def test_remaining_products(self):
        self.assertEqual(Product.objects.first().remaining_quantity, 198)

    def test_request_without_auth(self):
        response = self.client.get(self.route.format(Campaign.objects.first().code))
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_request_wrong_campaign_id(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format(Campaign.objects.last().code))
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Order not found.',
        )

    def test_request_inactive_campaign(self):
        self.client.force_authenticate(user=self.employee)
        campaign = Campaign.objects.first()
        campaign.status = 'PENDING'
        campaign.save()
        campaign.refresh_from_db()
        response = self.client.get(self.route.format(campaign.code))
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Order not found.',
        )

    def test_request_another_employees_order(self):
        self.client.force_authenticate(user=self.employee2)
        response = self.client.get(self.route.format(Campaign.objects.first().code))
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Order not found.',
        )

    def test_request_another_campaigns_order(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format(Campaign.objects.get(pk=2).code))
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Order not found.',
        )

    def test_request_success(self):
        self.maxDiff = None
        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format(Campaign.objects.first().code))
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))

        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'Employee order fetched successfully.',
                'status': 200,
                'data': {
                    'reference': 1,
                    'order_date_time': '2024-05-10T16:24:45Z',
                    'added_payment': False,
                    'full_name': 'First Last',
                    'phone_number': '0500000000',
                    'additional_phone_number': None,
                    'delivery_city': 'City name',
                    'delivery_street': 'Street name',
                    'delivery_street_number': '10',
                    'delivery_apartment_number': None,
                    'delivery_additional_details': None,
                    'products': [
                        {
                            'quantity': 2,
                            'product': {
                                'id': 1,
                                'name': 'name',
                                'description': 'desc en',
                                'sku': '123456',
                                'brand': {'name': 'brand1', 'logo_image': None},
                                'supplier': {'name': 'supplier1'},
                                'calculated_price': 4,
                                'categories': [],
                                'images': [],
                                'extra_price': 0,
                                'product_type': 'REGULAR',
                                'product_kind': 'PHYSICAL',
                                'link': '',
                                'technical_details': '',
                                'warranty': '',
                                'exchange_value': None,
                                'exchange_policy': '',
                                'remaining_quantity': 198,
                            },
                        }
                    ],
                },
            },
        )

    def test_request_success_with_added_payment(self):
        self.maxDiff = None
        order = Order.objects.first()
        order.cost_added = 1
        order.save()
        order.refresh_from_db()

        self.client.force_authenticate(user=self.employee)
        response = self.client.get(self.route.format(Campaign.objects.first().code))
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))

        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'Employee order fetched successfully.',
                'status': 200,
                'data': {
                    'reference': 1,
                    'order_date_time': '2024-05-10T16:24:45Z',
                    'added_payment': True,
                    'full_name': 'First Last',
                    'phone_number': '0500000000',
                    'additional_phone_number': None,
                    'delivery_city': 'City name',
                    'delivery_street': 'Street name',
                    'delivery_street_number': '10',
                    'delivery_apartment_number': None,
                    'delivery_additional_details': None,
                    'products': [
                        {
                            'quantity': 2,
                            'product': {
                                'id': 1,
                                'name': 'name',
                                'description': 'desc en',
                                'sku': '123456',
                                'brand': {'name': 'brand1', 'logo_image': None},
                                'supplier': {'name': 'supplier1'},
                                'calculated_price': 4,
                                'categories': [],
                                'images': [],
                                'extra_price': 0,
                                'product_type': 'REGULAR',
                                'product_kind': 'PHYSICAL',
                                'link': '',
                                'technical_details': '',
                                'warranty': '',
                                'exchange_value': None,
                                'exchange_policy': '',
                                'remaining_quantity': 198,
                            },
                        }
                    ],
                },
            },
        )


class CancelOrderViewTestCase(TestCase):
    fixtures = ['src/fixtures/cart_orders.json']

    def setUp(self):
        self.route = '/campaign/{}/cancel/order/{}'
        self.client = APIClient()
        self.employee = Employee.objects.first()
        self.employee2 = Employee.objects.create(
            first_name='employee_first_name',
            last_name='employee_last_name',
            auth_id='employee_auth_id',
            active=True,
            employee_group=EmployeeGroup.objects.first(),
        )

    def test_request_without_auth(self):
        response = self.client.put(
            self.route.format(Campaign.objects.first().code, Order.objects.first().pk)
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_request_wrong_campaign_code(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.put(
            self.route.format('0123456789012345', Order.objects.first().pk)
        )
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Order not found.',
        )

    def test_request_wrong_order(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.put(
            self.route.format(Campaign.objects.first().code, '2')
        )
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Order not found.',
        )

    def test_request_wrong_employee(self):
        self.client.force_authenticate(user=self.employee2)
        response = self.client.put(
            self.route.format(Campaign.objects.first().code, Order.objects.first().pk)
        )
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Order not found.',
        )

    def test_request_another_campaigns_order(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.put(
            self.route.format(Campaign.objects.get(pk=2).code, Order.objects.first().pk)
        )
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Order not found.',
        )

    def test_request_inactive_campaign(self):
        self.client.force_authenticate(user=self.employee)
        campaign = Campaign.objects.first()
        campaign.status = 'PENDING'
        campaign.save()
        campaign.refresh_from_db()
        response = self.client.put(
            self.route.format(campaign.code, Order.objects.first().pk)
        )
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Order not found.',
        )

    def test_request_order_has_cost_added(self):
        order = Order.objects.first()
        order.cost_added = 1
        order.save()
        order.refresh_from_db()

        self.client.force_authenticate(user=self.employee)
        response = self.client.put(
            self.route.format(Campaign.objects.first().code, Order.objects.first().pk)
        )
        self.assertEqual(response.status_code, 402)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'Cannot cancel paid order.',
        )
        self.assertEqual(
            content['code'],
            'order_paid',
        )

    def test_correct_request(self):
        self.client.force_authenticate(user=self.employee)
        order = Order.objects.first()
        self.assertEqual(order.status, 'PENDING')
        response = self.client.put(
            self.route.format(Campaign.objects.first().code, order.pk)
        )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(
            content['message'],
            'order canceled successfully.',
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatusEnum.CANCELLED.name)
        products = list(
            CartProduct.objects.filter(
                cart_id__campaign_employee_id__employee=self.employee
            )
        )
        self.assertEqual(products, [])


class EmployeeOrderViewTestCase(TestCase):
    fixtures = ['src/fixtures/inventory.json', 'src/fixtures/campaign.json']

    def setUp(self) -> None:
        self.route = '/campaign/{campaign_code}/order'
        self.client = APIClient()
        self.client.credentials(
            HTTP_X_AUTHORIZATION=f'Bearer {Employee.objects.get(pk=1).auth_id}'
        )
        self.cart = Cart.objects.get(
            campaign_employee_id=CampaignEmployee.objects.first()
        )
        CartProduct.objects.all().delete()
        CartProduct.objects.create(
            cart_id=self.cart,
            product_id=EmployeeGroupCampaignProduct.objects.first(),
            quantity=2,
        )
        CartProduct.objects.create(
            cart_id=self.cart,
            product_id=EmployeeGroupCampaignProduct.objects.get(pk=2),
            quantity=3,
        )
        return super().setUp()

    def tearDown(self) -> None:
        del self.route
        del self.client
        return super().tearDown()

    def _mock_response(
        self, status=200, content='CONTENT', json_data=None, raise_for_status=None
    ):
        mock_resp = mock.Mock()
        # mock raise_for_status call w/optional error
        mock_resp.raise_for_status = mock.Mock()
        if raise_for_status:
            mock_resp.raise_for_status.side_effect = raise_for_status
        # set status code and content
        mock_resp.status_code = status
        mock_resp.content = content
        # add json data if provided
        if json_data:
            mock_resp.json = mock.Mock(return_value=json_data)
        return mock_resp

    def test_request_without_auth(self):
        self.client.credentials(HTTP_X_AUTHORIZATION='')
        response = self.client.post(
            self.route.replace('{campaign_code}', str(Campaign.objects.get(pk=1).code))
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_campaign_not_exist_or_not_related(self):
        for campaign_code in [
            'invalid_campaign_code',
            str(Campaign.objects.get(pk=2).code),
        ]:
            response = self.client.post(
                self.route.replace('{campaign_code}', campaign_code)
            )
            self.assertEqual(response.status_code, 401)
            content = json.loads(response.content.decode(encoding='UTF-8'))
            self.assertDictEqual(
                content,
                {
                    'success': False,
                    'message': 'Bad credentials',
                    'code': 'bad_credentials',
                    'status': 401,
                    'data': {},
                },
            )

    def test_campaign_not_active(self):
        campaign = Campaign.objects.get(pk=1)
        campaign.status = Campaign.CampaignStatusEnum.FINISHED.name
        campaign.save()
        response = self.client.post(
            self.route.replace('{campaign_code}', str(Campaign.objects.get(pk=1).code))
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_invalid_request_data_errors(self):
        response = self.client.post(
            self.route.replace('{campaign_code}', str(Campaign.objects.get(pk=1).code)),
            format='json',
            data={},
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {
                    'full_name': ['This field is required.'],
                    'phone_number': ['This field is required.'],
                    'delivery_city': ['This field is required.'],
                    'delivery_street': ['This field is required.'],
                    'delivery_street_number': ['This field is required.'],
                },
            },
        )

    def test_employee_group_campaign_not_exist(self):
        EmployeeGroupCampaign.objects.all().delete()
        response = self.client.post(
            self.route.replace('{campaign_code}', str(Campaign.objects.get(pk=1).code))
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_employee_group_campaign_not_related(self):
        EmployeeGroupCampaign.objects.filter(
            employee_group=EmployeeGroup.objects.get(pk=1)
        ).delete()
        response = self.client.post(
            self.route.replace('{campaign_code}', str(Campaign.objects.get(pk=1).code))
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_employee_group_cart_not_found(self):
        self.cart.delete()
        response = self.client.post(
            self.route.replace('{campaign_code}', str(Campaign.objects.get(pk=1).code)),
            format='json',
            data={
                'full_name': 'First Last',
                'phone_number': '0500000000',
                'delivery_city': 'City name',
                'delivery_street': 'Street name',
                'delivery_street_number': 10,
            },
        )
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Cart not found.',
                'code': 'not_found',
                'status': 404,
                'data': {},
            },
        )

    def test_employee_group_empty_cart(self):
        CartProduct.objects.all().delete()
        response = self.client.post(
            self.route.replace('{campaign_code}', str(Campaign.objects.get(pk=1).code)),
            format='json',
            data={
                'full_name': 'First Last',
                'phone_number': '0500000000',
                'delivery_city': 'City name',
                'delivery_street': 'Street name',
                'delivery_street_number': 10,
            },
        )
        self.assertEqual(response.status_code, 404)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Empty cart.',
                'code': 'not_found',
                'status': 404,
                'data': {},
            },
        )

    def test_employee_order_already_exists(self):
        Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.first(),
            order_date_time=datetime.now(timezone.utc),
            cost_from_budget=50,
            cost_added=0,
            status=Order.OrderStatusEnum.PENDING.name,
        )

        response = self.client.post(
            self.route.replace('{campaign_code}', str(Campaign.objects.get(pk=1).code)),
            format='json',
            data={
                'full_name': 'First Last',
                'phone_number': '0500000000',
                'delivery_city': 'City name',
                'delivery_street': 'Street name',
                'delivery_street_number': 10,
            },
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Employee already ordered.',
                'code': 'already_ordered',
                'status': 400,
                'data': {},
            },
        )

    @mock.patch('requests.post')
    def test_valid_request(self, mock_post):
        mock_post.return_value = self._mock_response(
            json_data={
                'status': 1,
                'data': {
                    'processToken': 'token',
                    'processId': 1234,
                    'authCode': 'abcdefg1234',
                },
            }
        )

        campaign_code = Campaign.objects.get(pk=1).code
        response = self.client.post(
            self.route.replace('{campaign_code}', campaign_code),
            format='json',
            data={
                'full_name': 'First Last',
                'phone_number': '0500000000',
                'delivery_city': 'City name',
                'delivery_street': 'Street name',
                'delivery_street_number': 10,
            },
        )
        self.assertEqual(response.status_code, 402)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Order payment required.',
                'status': 402,
                'data': {
                    'payment_code': 'abcdefg1234',
                },
            },
        )
        self.assertListEqual(
            list(
                Order.objects.first()
                .orderproduct_set.all()
                .values('product_id', 'quantity')
            ),
            [{'product_id': 1, 'quantity': 2}, {'product_id': 2, 'quantity': 3}],
        )

        _, kwargs = mock_post.call_args
        self.assertDictEqual(
            kwargs,
            {
                'data': {
                    'pageCode': None,
                    'userId': None,
                    'apiKey': None,
                    'sum': 4,
                    'description': 'product name en 1 x 2, product name en 2 x 3',
                    'pageField[fullName]': 'First Last',
                    'pageField[phone]': '0500000000',
                    'pageField[invoiceName]': 'Invoice 1',
                    'successUrl': (
                        f'{settings.EMPLOYEE_SITE_BASE_URL}/{campaign_code}/order'
                    ),
                    'cancelUrl': (
                        f'{settings.EMPLOYEE_SITE_BASE_URL}/{campaign_code}/checkout'
                    ),
                    'cField1': None,
                }
            },
        )

    def test_checkout_global_without_country_or_state_code_or_zip_code(self):
        EmployeeGroupCampaign.objects.filter(pk='1').update(check_out_location='GLOBAL')

        campaign_code = Campaign.objects.get(pk=1).code
        response = self.client.post(
            self.route.replace('{campaign_code}', campaign_code),
            format='json',
            data={
                'full_name': 'First Last',
                'phone_number': '0500000000',
                'delivery_city': 'City name',
                'delivery_street': 'Street name',
                'delivery_street_number': 10,
                'country': 'US',
                'zip_code': '10000',
            },
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {'state_code': ['This field is required.']},
            },
        )

        response = self.client.post(
            self.route.replace('{campaign_code}', campaign_code),
            format='json',
            data={
                'full_name': 'First Last',
                'phone_number': '0500000000',
                'delivery_city': 'City name',
                'delivery_street': 'Street name',
                'delivery_street_number': 10,
                'country': 'US',
                'state_code': '11',
            },
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {'zip_code': ['This field is required.']},
            },
        )

        response = self.client.post(
            self.route.replace('{campaign_code}', campaign_code),
            format='json',
            data={
                'full_name': 'First Last',
                'phone_number': '0500000000',
                'delivery_city': 'City name',
                'delivery_street': 'Street name',
                'delivery_street_number': 10,
                'state_code': '11',
                'zip_code': '10000',
            },
        )
        self.assertEqual(response.status_code, 400)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {'country': ['This field is required.']},
            },
        )

    @mock.patch('requests.post')
    def test_valid_checkout_global_request(self, mock_post):
        EmployeeGroupCampaign.objects.filter(pk='1').update(
            check_out_location='GLOBAL', budget_per_employee=5
        )

        mock_post.return_value = self._mock_response(
            json_data={
                'status': 1,
                'data': {
                    'processToken': 'token',
                    'processId': 1234,
                    'authCode': 'abcdefg1234',
                },
            }
        )

        campaign_code = Campaign.objects.get(pk=1).code
        response = self.client.post(
            self.route.replace('{campaign_code}', campaign_code),
            format='json',
            data={
                'full_name': 'First Last',
                'phone_number': '0500000000',
                'delivery_city': 'City name',
                'delivery_street': 'Street name',
                'delivery_street_number': 10,
                'country': 'US',
                'state_code': '11',
                'zip_code': '10000',
                'color': 'white',
                'size': 'L',
            },
        )
        order = Order.objects.first()
        self.assertEqual(order.country, 'US')
        self.assertEqual(order.state_code, '11')
        self.assertEqual(order.zip_code, '10000')
        self.assertEqual(order.color, 'white')
        self.assertEqual(order.size, 'L')
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': True,
                'message': 'Order placed successfully.',
                'status': 200,
                'data': {'reference': 1},
            },
        )
        self.assertListEqual(
            list(
                Order.objects.first()
                .orderproduct_set.all()
                .values('product_id', 'quantity')
            ),
            [{'product_id': 1, 'quantity': 2}, {'product_id': 2, 'quantity': 3}],
        )

    @mock.patch('requests.post')
    def test_request_cost_with_multiple_employee_group_budgets(self, mock_post):
        second_cart = Cart.objects.get(
            campaign_employee_id=CampaignEmployee.objects.get(pk=2)
        )
        CartProduct.objects.create(
            cart_id=second_cart,
            product_id=EmployeeGroupCampaignProduct.objects.first(),
            quantity=2,
        )
        CartProduct.objects.create(
            cart_id=second_cart,
            product_id=EmployeeGroupCampaignProduct.objects.get(pk=2),
            quantity=3,
        )

        mock_post.return_value = self._mock_response(
            json_data={
                'status': 1,
                'data': {
                    'processToken': 'token',
                    'processId': 1234,
                    'authCode': 'abcdefg1234',
                },
            }
        )

        self.client.force_authenticate(user=Employee.objects.get(pk=2))
        campaign_code = Campaign.objects.get(pk=1).code
        response = self.client.post(
            self.route.replace('{campaign_code}', campaign_code),
            format='json',
            data={
                'full_name': 'First Last',
                'phone_number': '0500000000',
                'delivery_city': 'City name',
                'delivery_street': 'Street name',
                'delivery_street_number': 10,
            },
        )
        self.assertEqual(response.status_code, 402)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {
                'success': False,
                'message': 'Order payment required.',
                'status': 402,
                'data': {
                    'payment_code': 'abcdefg1234',
                },
            },
        )

        # check the call args to the create payment process endpoint - the sum
        # should be based off of the second employee group's budget and not any
        # other group's budget
        _, kwargs = mock_post.call_args
        self.assertDictEqual(
            kwargs,
            {
                'data': {
                    'pageCode': None,
                    'userId': None,
                    'apiKey': None,
                    'sum': 3,
                    'description': 'product name en 1 x 2, product name en 2 x 3',
                    'pageField[fullName]': 'First Last',
                    'pageField[phone]': '0500000000',
                    'pageField[invoiceName]': 'Invoice 1',
                    'successUrl': (
                        f'{settings.EMPLOYEE_SITE_BASE_URL}/{campaign_code}/order'
                    ),
                    'cancelUrl': (
                        f'{settings.EMPLOYEE_SITE_BASE_URL}/{campaign_code}/checkout'
                    ),
                    'cField1': None,
                }
            },
        )


class CartAddProductTestCase(TestCase):
    fixtures = ['src/fixtures/inventory.json', 'src/fixtures/campaign.json']

    def assert_request(
        self, campaign_code, auth_token, request_json, response_status, response_json
    ):
        client = APIClient()
        response = client.post(
            path=f'/campaign/{campaign_code}/cart/add_product',
            format='json',
            headers={'X-Authorization': f'Bearer {auth_token}'},
            data=request_json,
        )
        self.assertEqual(response.status_code, response_status)
        self.assertDictEqual(response.json(), response_json)
        return response

    def setUp(self):
        self.employee1 = Employee.objects.first()
        self.employeegroup1 = self.employee1.employee_group
        self.campaignemployee1 = CampaignEmployee.objects.filter(
            employee=self.employee1,
            campaign__status=Campaign.CampaignStatusEnum.ACTIVE.name,
        ).first()
        self.campaign1 = self.campaignemployee1.campaign
        self.egc1 = EmployeeGroupCampaign.objects.filter(
            employee_group=self.employeegroup1, campaign=self.campaign1
        ).first()
        self.egcp1 = EmployeeGroupCampaignProduct.objects.filter(
            employee_group_campaign_id=self.egc1
        ).first()
        self.cart1 = Cart.objects.filter(
            campaign_employee_id=self.campaignemployee1
        ).first()
        self.cartproduct1 = CartProduct.objects.filter(
            cart_id=self.cart1, product_id=self.egcp1
        )

    def test_campaign_invalid(self):
        self.assert_request(
            campaign_code='invalid_campaign_code',
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 1,
            },
            response_status=401,
            response_json={
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_campaign_employee_not_related(self):
        employee_not_related = Employee.objects.exclude(
            employee_group=self.employeegroup1
        ).first()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=employee_not_related.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 1,
            },
            response_status=401,
            response_json={
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_campaign_inactive(self):
        self.campaign1.status = Campaign.CampaignStatusEnum.PENDING.name
        self.campaign1.save()
        self.campaign1.refresh_from_db()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 1,
            },
            response_status=401,
            response_json={
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_employee_invalid(self):
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token='invalid_employee',
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 1,
            },
            response_status=401,
            response_json={'detail': 'Authentication credentials were not provided.'},
        )

    def test_request_json_empty(self):
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={},
            response_status=400,
            response_json={
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {
                    'product_id': ['This field is required.'],
                    'quantity': ['This field is required.'],
                },
            },
        )

    def test_request_json_invalid(self):
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': 'invalid_product_id',
                'quantity': 'invalid_quantity',
            },
            response_status=400,
            response_json={
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {
                    'product_id': ['A valid integer is required.'],
                    'quantity': ['A valid integer is required.'],
                },
            },
        )

    def test_product_not_exist(self):
        product_not_exist = EmployeeGroupCampaignProduct.objects.last().pk + 1
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': product_not_exist,
                'quantity': 10,
            },
            response_status=401,
            response_json={
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_product_not_related(self):
        product_not_related = EmployeeGroupCampaignProduct.objects.exclude(
            employee_group_campaign_id=self.egc1
        ).first()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': product_not_related.pk,
                'quantity': 1,
            },
            response_status=401,
            response_json={
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_campaignemployee_not_exist(self):
        CampaignEmployee.objects.all().delete()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 1,
            },
            response_status=401,
            response_json={
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_notcart(self):
        expected_cart_id = Cart.objects.all().count() + 1
        Cart.objects.all().delete()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={'product_id': self.egcp1.pk, 'quantity': 0},
            response_status=200,
            response_json={
                'success': True,
                'message': 'Cart updated successfully.',
                'status': 200,
                'data': {'cart_id': expected_cart_id},
            },
        )
        carts = Cart.objects.all()
        self.assertEqual(carts.count(), 1)
        self.assertTrue(carts.first().pk, expected_cart_id)

    def test_notmultiselection_zeroquantity(self):
        self.egc1.product_selection_mode = (
            EmployeeGroupCampaign.ProductSelectionTypeEnum.SINGLE.name
        )
        self.egc1.save()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 0,
            },
            response_status=200,
            response_json={
                'success': True,
                'message': 'Cart updated successfully.',
                'status': 200,
                'data': {'cart_id': self.cart1.pk},
            },
        )
        self.assertFalse(CartProduct.objects.all())

    def test_notmultiselection_positivequantity(self):
        self.egc1.product_selection_mode = (
            EmployeeGroupCampaign.ProductSelectionTypeEnum.SINGLE.name
        )
        self.egc1.save()
        existing_cart_products = list(self.cartproduct1.values_list('pk', flat=True))
        self.assertTrue(existing_cart_products)
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 1,
            },
            response_status=200,
            response_json={
                'success': True,
                'message': 'Cart updated successfully.',
                'status': 200,
                'data': {'cart_id': self.cart1.pk},
            },
        )
        self.assertFalse(
            CartProduct.objects.filter(pk__in=existing_cart_products),
        )
        cart_products = CartProduct.objects.filter(
            cart_id=self.cart1.pk, product_id=self.egcp1.pk
        )
        self.assertEqual(cart_products.count(), 1)
        self.assertTrue(cart_products.first().quantity, 1)

    def test_multiselection_notcartproduct_zeroquantity(self):
        self.egc1.product_selection_mode = (
            EmployeeGroupCampaign.ProductSelectionTypeEnum.MULTIPLE.name
        )
        self.egc1.save()
        CartProduct.objects.all().delete()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 0,
            },
            response_status=200,
            response_json={
                'success': True,
                'message': 'Cart updated successfully.',
                'status': 200,
                'data': {'cart_id': self.cart1.pk},
            },
        )
        self.assertFalse(CartProduct.objects.all())

    def test_multiselection_notcartproduct_positivequantity(self):
        self.egc1.product_selection_mode = (
            EmployeeGroupCampaign.ProductSelectionTypeEnum.MULTIPLE.name
        )
        self.egc1.save()
        CartProduct.objects.all().delete()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 1,
            },
            response_status=200,
            response_json={
                'success': True,
                'message': 'Cart updated successfully.',
                'status': 200,
                'data': {'cart_id': self.cart1.pk},
            },
        )
        cart_products = CartProduct.objects.filter(
            cart_id=self.cart1.pk, product_id=self.egcp1.pk
        )
        self.assertEqual(cart_products.count(), 1)
        self.assertTrue(cart_products.first().quantity, 1)

    def test_multiselection_cartproduct_zeroquantity(self):
        self.egc1.product_selection_mode = (
            EmployeeGroupCampaign.ProductSelectionTypeEnum.MULTIPLE.name
        )
        self.egc1.save()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 0,
            },
            response_status=200,
            response_json={
                'success': True,
                'message': 'Cart updated successfully.',
                'status': 200,
                'data': {'cart_id': self.cart1.pk},
            },
        )
        cart_products = CartProduct.objects.filter(
            cart_id=self.cart1.pk, product_id=self.egcp1.pk
        )
        zeroquantity_cartproducts = cart_products.filter(quantity=0)
        self.assertFalse(zeroquantity_cartproducts)

    def test_multiselection_cartproduct_positivequantity(self):
        self.egc1.product_selection_mode = (
            EmployeeGroupCampaign.ProductSelectionTypeEnum.MULTIPLE.name
        )
        self.egc1.save()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee1.auth_id,
            request_json={
                'product_id': self.egcp1.pk,
                'quantity': 2,
            },
            response_status=200,
            response_json={
                'success': True,
                'message': 'Cart updated successfully.',
                'status': 200,
                'data': {'cart_id': self.cart1.pk},
            },
        )
        cart_products = CartProduct.objects.filter(
            cart_id=self.cart1.pk, product_id=self.egcp1.pk
        )
        self.assertEqual(
            set(cart_products.values_list('quantity', flat=True)),
            {2},
        )


class FetchCartProducts(TestCase):
    fixtures = ['src/fixtures/inventory.json', 'src/fixtures/campaign.json']

    def setUp(self):
        self.client = APIClient()
        self.employee1 = Employee.objects.first()
        self.employeegroup1 = self.employee1.employee_group
        self.campaignemployee1 = CampaignEmployee.objects.filter(
            employee=self.employee1,
            campaign__status=Campaign.CampaignStatusEnum.ACTIVE.name,
        ).first()
        self.campaign1 = self.campaignemployee1.campaign
        self.egc1 = EmployeeGroupCampaign.objects.filter(
            employee_group=self.employeegroup1, campaign=self.campaign1
        ).first()
        self.egcp1 = EmployeeGroupCampaignProduct.objects.filter(
            employee_group_campaign_id=self.egc1
        ).first()
        self.cart1 = Cart.objects.filter(
            campaign_employee_id=self.campaignemployee1
        ).first()
        self.cartproduct1 = CartProduct.objects.filter(
            cart_id=self.cart1, product_id=self.egcp1
        )
        ProductImage.objects.create(
            product=self.egcp1.product_id, main=True, image='abc.jpeg'
        )
        self.route = '/campaign/{}/cart/products/'

        OrganizationProduct.objects.create(
            organization=self.campaign1.organization,
            product=self.egcp1.product_id,
            price=10,
        )

    def test_fetch_cart_products_guest_user(self):
        response = self.client.get(self.route.format(self.campaign1.code))
        self.assertEqual(response.status_code, 401)

    def test_fetch_cart_products_loggedin_user(self):
        self.client.force_authenticate(user=self.employee1)
        response = self.client.get(self.route.format(self.campaign1.code))
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content.get('data'),
            {
                'products': [
                    {
                        'id': 1,
                        'product': {
                            'id': 1,
                            'name': 'product name en 1',
                            'description': 'description 1',
                            'sku': 'sku 1',
                            'link': '',
                            'technical_details': '',
                            'warranty': '',
                            'exchange_value': None,
                            'exchange_policy': '',
                            'product_type': 'REGULAR',
                            'product_kind': 'PHYSICAL',
                            'brand': {
                                'name': 'brand name en 1',
                                'logo_image': None,
                            },
                            'supplier': {
                                'name': 'supplier name en 1',
                            },
                            'images': [
                                {'main': True, 'image': '/media/abc.jpeg'},
                            ],
                            'categories': [],
                            'calculated_price': 10,
                            'extra_price': 9,
                            'remaining_quantity': 200,
                        },
                        'quantity': 1,
                    },
                    {
                        'id': 2,
                        'product': {
                            'id': 2,
                            'name': 'product name en 2',
                            'description': 'description 1',
                            'sku': 'sku 2',
                            'link': '',
                            'technical_details': '',
                            'warranty': '',
                            'exchange_value': None,
                            'exchange_policy': '',
                            'product_type': 'REGULAR',
                            'product_kind': 'PHYSICAL',
                            'brand': {
                                'name': 'brand name en 1',
                                'logo_image': None,
                            },
                            'supplier': {
                                'name': 'supplier name en 1',
                            },
                            'images': [],
                            'categories': [],
                            'calculated_price': 1,
                            'extra_price': 0,
                            'remaining_quantity': 200,
                        },
                        'quantity': 0,
                    },
                ],
            },
        )


class ShareProductViewTestCase(TestCase):
    fixtures = ['src/fixtures/campaign.json', 'src/fixtures/inventory.json']

    def assert_request(
        self, campaign_code, auth_token, request_json, response_status, response_json
    ):
        response = self.client.post(
            path=f'/campaign/{campaign_code}/share/',
            format='json',
            headers={'X-Authorization': f'Bearer {auth_token}'},
            data=request_json,
        )
        self.assertEqual(response.status_code, response_status)
        self.assertDictEqual(response.json(), response_json)
        return response

    def setUp(self):
        self.client = APIClient()
        self.employee_1 = Employee.objects.first()
        self.client.force_authenticate(user=self.employee_1)

        self.share_type_1 = ShareTypeEnum
        self.product_ids_1 = Product.objects.values_list('id', flat=True)
        self.campaignemployee1 = CampaignEmployee.objects.filter(
            employee=self.employee_1,
            campaign__status=Campaign.CampaignStatusEnum.ACTIVE.name,
        ).first()
        self.campaign1 = self.campaignemployee1.campaign
        self.valid_share_data = {
            'share_type': self.share_type_1.Product.value,
            'product_ids': [self.product_ids_1[0]],
        }

    def test_successful_share(self):
        response = self.client.post(
            path=f'/campaign/{self.campaign1.code}/share/',
            format='json',
            headers={'X-Authorization': f'Bearer {self.employee_1.auth_id}'},
            data=self.valid_share_data,
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Products shared successfully.',
                'status': 200,
                'data': {'share_id': str(Share.objects.first().share_id)},
            },
        )

    def test_campaign_invalid(self):
        self.assert_request(
            campaign_code='invalid_campaign_code',
            auth_token=self.employee_1.auth_id,
            request_json=self.valid_share_data,
            response_status=404,
            response_json={
                'code': 'not_found',
                'message': 'Campaign not found or inactive.',
                'status': 404,
                'success': False,
            },
        )

    def test_campaign_inactive(self):
        self.campaign1.status = 'PENDING'
        self.campaign1.save()
        self.campaign1.refresh_from_db()
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee_1.auth_id,
            request_json=self.valid_share_data,
            response_status=404,
            response_json={
                'success': False,
                'message': 'Campaign not found or inactive.',
                'code': 'not_found',
                'status': 404,
            },
        )

    def test_invalid_share_type(self):
        update_share_data = self.valid_share_data
        update_share_data['share_type'] = 'INVALID_SHARE_TYPE'
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee_1.auth_id,
            request_json=update_share_data,
            response_status=400,
            response_json={
                'success': False,
                'message': 'Invalid share type provided.',
                'code': 'invalid_share_type',
                'status': 400,
            },
        )

    def test_request_json_empty(self):
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee_1.auth_id,
            request_json={},
            response_status=400,
            response_json={
                'product_ids': ['This field is required.'],
                'share_type': ['This field is required.'],
            },
        )

    def test_request_json_invalid(self):
        update_share_data = self.valid_share_data
        update_share_data['product_ids'] = 'invalid_product_id'
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee_1.auth_id,
            request_json=update_share_data,
            response_status=400,
            response_json={
                'product_ids': ['Expected a list of items but got type "str".']
            },
        )

    def test_product_not_exist(self):
        update_share_data = self.valid_share_data
        update_share_data['product_ids'] = ['10000']
        self.assert_request(
            campaign_code=self.campaign1.code,
            auth_token=self.employee_1.auth_id,
            request_json=update_share_data,
            response_status=404,
            response_json={
                'success': False,
                'message': "Product(s) doesn't exist or not active in the campaign",
                'code': 'not_found',
                'status': 404,
            },
        )

    def test_not_authenticated_employee(self):
        self.client.force_authenticate(user=None)  # Unauthenticated
        response = self.client.post(
            f'/campaign/{self.campaign1.code}/share/',
            data=json.dumps(self.valid_share_data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
        content = json.loads(response.content.decode('UTF-8'))
        self.assertDictEqual(
            content,
            {'detail': 'Authentication credentials were not provided.'},
        )


class GetShareDetailsViewTestCase(TestCase):
    fixtures = ['src/fixtures/campaign.json', 'src/fixtures/inventory.json']

    def assert_request(self, share_id, response_status, response_json):
        response = self.client.get(
            path=f'/campaign/share/{share_id}/',
            format='json',
        )
        self.assertEqual(response.status_code, response_status)
        self.assertDictEqual(response.json(), response_json)
        return response

    def setUp(self):
        self.client = APIClient()
        self.employee_1 = Employee.objects.first()
        self.employee_group1 = self.employee_1.employee_group
        self.campaignemployee1 = CampaignEmployee.objects.filter(
            employee=self.employee_1,
            campaign__status=Campaign.CampaignStatusEnum.ACTIVE.name,
        ).first()
        self.campaign1 = self.campaignemployee1.campaign
        self.egc1 = EmployeeGroupCampaign.objects.filter(
            employee_group=self.employee_group1, campaign=self.campaign1
        ).first()
        self.campaignemployee1 = CampaignEmployee.objects.filter(
            employee=self.employee_1,
            campaign__status=Campaign.CampaignStatusEnum.ACTIVE.name,
        ).first()
        self.campaign1 = self.campaignemployee1.campaign

        self.share1 = Share.objects.create(
            share_type='Product',
            campaign_code=self.campaign1.code,
            owner=self.employee_1,
        )

        self.share2 = Share.objects.create(
            share_type='Cart',
            campaign_code=self.campaign1.code,
            owner=self.employee_1,
        )

    def test_share_notfound(self):
        self.assert_request(
            share_id='aaa78629-2013-4389-996a-b90955fb796a',
            response_status=404,
            response_json={
                'success': False,
                'code': 'not_found',
                'message': 'Share not found.',
                'status': 404,
            },
        )

    def test_share_nodata(self):
        self.assert_request(
            share_id=self.share1.share_id,
            response_status=200,
            response_json={
                'success': True,
                'data': {'cart': None, 'products': [], 'share_type': 'Product'},
                'message': 'Share details fetched successfully.',
                'status': 200,
            },
        )

    def test_share_product(self):
        egcp = EmployeeGroupCampaignProduct.objects.first()
        self.share1.products.add(egcp.product_id)
        self.share1.save()
        self.share1.refresh_from_db()
        self.assert_request(
            share_id=self.share1.share_id,
            response_status=200,
            response_json={
                'success': True,
                'message': 'Share details fetched successfully.',
                'status': 200,
                'data': {
                    'share_type': 'Product',
                    'products': [
                        {
                            'id': 1,
                            'name': 'product name en 1',
                            'description': 'description 1',
                            'sku': 'sku 1',
                            'link': '',
                            'technical_details': '',
                            'warranty': '',
                            'exchange_value': None,
                            'exchange_policy': '',
                            'product_type': 'REGULAR',
                            'product_kind': 'PHYSICAL',
                            'brand': {'name': 'brand name en 1', 'logo_image': None},
                            'supplier': {'name': 'supplier name en 1'},
                            'images': [],
                            'categories': [],
                            'calculated_price': 1,
                            'extra_price': 0,
                            'remaining_quantity': 200,
                        }
                    ],
                    'cart': None,
                    'budget_per_employee': 1,
                    'displayed_currency': 'CURRENCY',
                },
            },
        )

    def test_share_product_coin(self):
        egcp = EmployeeGroupCampaignProduct.objects.first()
        self.egc1.displayed_currency = 'Coins'
        self.egc1.save()
        self.egc1.refresh_from_db()

        self.share1.products.add(egcp.product_id)
        self.share1.save()
        self.share1.refresh_from_db()
        self.assert_request(
            share_id=self.share1.share_id,
            response_status=200,
            response_json={
                'success': True,
                'message': 'Share details fetched successfully.',
                'status': 200,
                'data': {
                    'share_type': 'Product',
                    'products': [
                        {
                            'id': 1,
                            'name': 'product name en 1',
                            'description': 'description 1',
                            'sku': 'sku 1',
                            'link': '',
                            'technical_details': '',
                            'warranty': '',
                            'exchange_value': None,
                            'exchange_policy': '',
                            'product_type': 'REGULAR',
                            'product_kind': 'PHYSICAL',
                            'brand': {'name': 'brand name en 1', 'logo_image': None},
                            'supplier': {'name': 'supplier name en 1'},
                            'images': [],
                            'categories': [],
                            'calculated_price': 1,
                            'extra_price': 0,
                            'remaining_quantity': 200,
                        }
                    ],
                    'cart': None,
                    'budget_per_employee': 1,
                    'displayed_currency': 'Coins',
                },
            },
        )

    def test_share_cart(self):
        egcp = EmployeeGroupCampaignProduct.objects.first()
        self.share2.products.add(egcp.product_id)
        self.share2.save()
        self.share2.refresh_from_db()
        self.assert_request(
            share_id=self.share2.share_id,
            response_status=200,
            response_json={
                'success': True,
                'message': 'Share details fetched successfully.',
                'status': 200,
                'data': {
                    'share_type': 'Cart',
                    'products': [],
                    'cart': {
                        'products': [
                            {
                                'id': 1,
                                'product': {
                                    'id': 1,
                                    'name': 'product name en 1',
                                    'description': 'description 1',
                                    'sku': 'sku 1',
                                    'link': '',
                                    'technical_details': '',
                                    'warranty': '',
                                    'exchange_value': None,
                                    'exchange_policy': '',
                                    'product_type': 'REGULAR',
                                    'product_kind': 'PHYSICAL',
                                    'brand': {
                                        'name': 'brand name en 1',
                                        'logo_image': None,
                                    },
                                    'supplier': {'name': 'supplier name en 1'},
                                    'images': [],
                                    'categories': [],
                                    'calculated_price': 1,
                                    'extra_price': 0,
                                    'remaining_quantity': 200,
                                },
                                'quantity': 1,
                            },
                            {
                                'id': 2,
                                'product': {
                                    'id': 2,
                                    'name': 'product name en 2',
                                    'description': 'description 1',
                                    'sku': 'sku 2',
                                    'link': '',
                                    'technical_details': '',
                                    'warranty': '',
                                    'exchange_value': None,
                                    'exchange_policy': '',
                                    'product_type': 'REGULAR',
                                    'product_kind': 'PHYSICAL',
                                    'brand': {
                                        'name': 'brand name en 1',
                                        'logo_image': None,
                                    },
                                    'supplier': {'name': 'supplier name en 1'},
                                    'images': [],
                                    'categories': [],
                                    'calculated_price': 1,
                                    'extra_price': 0,
                                    'remaining_quantity': 200,
                                },
                                'quantity': 0,
                            },
                        ]
                    },
                    'budget_per_employee': 1,
                    'displayed_currency': 'CURRENCY',
                },
            },
        )

    def test_share_cart_coin(self):
        egcp = EmployeeGroupCampaignProduct.objects.first()
        self.egc1.displayed_currency = 'Coins'
        self.egc1.save()
        self.egc1.refresh_from_db()

        self.share2.products.add(egcp.product_id)
        self.share2.save()
        self.share2.refresh_from_db()
        self.assert_request(
            share_id=self.share2.share_id,
            response_status=200,
            response_json={
                'success': True,
                'message': 'Share details fetched successfully.',
                'status': 200,
                'data': {
                    'share_type': 'Cart',
                    'products': [],
                    'cart': {
                        'products': [
                            {
                                'id': 1,
                                'product': {
                                    'id': 1,
                                    'name': 'product name en 1',
                                    'description': 'description 1',
                                    'sku': 'sku 1',
                                    'link': '',
                                    'technical_details': '',
                                    'warranty': '',
                                    'exchange_value': None,
                                    'exchange_policy': '',
                                    'product_type': 'REGULAR',
                                    'product_kind': 'PHYSICAL',
                                    'brand': {
                                        'name': 'brand name en 1',
                                        'logo_image': None,
                                    },
                                    'supplier': {'name': 'supplier name en 1'},
                                    'images': [],
                                    'categories': [],
                                    'calculated_price': 1,
                                    'extra_price': 0,
                                    'remaining_quantity': 200,
                                },
                                'quantity': 1,
                            },
                            {
                                'id': 2,
                                'product': {
                                    'id': 2,
                                    'name': 'product name en 2',
                                    'description': 'description 1',
                                    'sku': 'sku 2',
                                    'link': '',
                                    'technical_details': '',
                                    'warranty': '',
                                    'exchange_value': None,
                                    'exchange_policy': '',
                                    'product_type': 'REGULAR',
                                    'product_kind': 'PHYSICAL',
                                    'brand': {
                                        'name': 'brand name en 1',
                                        'logo_image': None,
                                    },
                                    'supplier': {'name': 'supplier name en 1'},
                                    'images': [],
                                    'categories': [],
                                    'calculated_price': 1,
                                    'extra_price': 0,
                                    'remaining_quantity': 200,
                                },
                                'quantity': 0,
                            },
                        ]
                    },
                    'budget_per_employee': 1,
                    'displayed_currency': 'Coins',
                },
            },
        )


class CampaignOffersViewTestCase(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.route = '/campaign/quick-offer'
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})

    def test_request_without_auth(self):
        QuickOffer.objects.update(status='ACTIVE')
        print(QuickOffer.objects.first().organization.logo_image)
        print('print_logo_image')
        self.quick_offer.refresh_from_db()
        response = self.client.get(
            f'{self.route}/{self.quick_offer.code}',
        )
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            content.get('data'),
            QuickOfferReadOnlySerializer(self.quick_offer).data,
        )

    def test_request_not_active_offer(self):
        QuickOffer.objects.update(status='PENDING')
        response = self.client.get(
            f'{self.route}/{QuickOffer.objects.first().code}',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 403)
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertDictEqual(
            content,
            {'detail': 'You do not have permission to perform this action.'},
        )

    def test_request_valid_request(self):
        QuickOffer.objects.update(status='ACTIVE')
        self.quick_offer.refresh_from_db()
        response = self.client.get(
            f'{self.route}/{self.quick_offer.code}',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        content = json.loads(response.content.decode(encoding='UTF-8'))
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            content.get('data'),
            QuickOfferSerializer(self.quick_offer).data,
        )


class OrganizationQuickOfferLoginView(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()

    def test_quick_offer_not_found(self):
        response = self.client.post(
            '/campaign/invalid_quick_offer_code/quick-offer-login'
        )
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_quick_offer_not_active(self):
        self.quick_offer.status = QuickOffer.StatusEnum.PENDING.name
        self.quick_offer.save()
        response = self.client.post(
            f'/campaign/{self.quick_offer.code}/quick-offer-login'
        )
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_invalid_auth_id(self):
        self.quick_offer.auth_method = QuickOffer.AuthMethodEnum.AUTH_ID.name
        self.quick_offer.save()
        response = self.client.post(
            f'/campaign/{self.quick_offer.code}/quick-offer-login',
            format='json',
            data={
                'auth_id': 'invalid_auth_id',
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    def test_valid_auth_id(self):
        self.quick_offer.auth_method = QuickOffer.AuthMethodEnum.AUTH_ID.name
        self.quick_offer.save()
        response = self.client.post(
            f'/campaign/{self.quick_offer.code}/quick-offer-login',
            format='json',
            data={
                'auth_id': self.quick_offer.auth_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Organization logged in successfully',
                'status': 200,
                'data': {
                    'auth_token': jwt_encode({'quick_offer_id': self.quick_offer.pk}),
                },
            },
        )

    def test_invalid_otp(self):
        response = self.client.post(
            f'/campaign/{self.quick_offer.code}/quick-offer-login',
            format='json',
            data={'otp': 'invalid_otp'},
        )
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Bad credentials',
                'code': 'bad_credentials',
                'status': 401,
                'data': {},
            },
        )

    @mock.patch('campaign.views.send_otp_token_email')
    def test_email(self, mock_send_otp_token_email):
        self.quick_offer.auth_method = QuickOffer.AuthMethodEnum.EMAIL.name
        self.quick_offer.save()
        response = self.client.post(
            f'/campaign/{self.quick_offer.code}/quick-offer-login',
        )
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Missing OTP code',
                'code': 'missing_otp',
                'status': 401,
                'data': {},
            },
        )
        mock_send_otp_token_email.assert_called()
        _, kwargs = mock_send_otp_token_email.call_args
        self.quick_offer.refresh_from_db()
        self.assertEqual(kwargs['email'], self.quick_offer.email)
        otp = kwargs['otp_token']
        response = self.client.post(
            f'/campaign/{self.quick_offer.code}/quick-offer-login',
            format='json',
            data={'otp': otp},
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Organization logged in successfully',
                'status': 200,
                'data': {
                    'auth_token': jwt_encode({'quick_offer_id': self.quick_offer.pk}),
                },
            },
        )

    @mock.patch('campaign.views.send_otp_token_sms')
    def test_phone_number(self, mock_send_otp_token_sms):
        self.quick_offer.auth_method = QuickOffer.AuthMethodEnum.PHONE_NUMBER.name
        self.quick_offer.save()
        response = self.client.post(
            f'/campaign/{self.quick_offer.code}/quick-offer-login',
        )
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Missing OTP code',
                'code': 'missing_otp',
                'status': 401,
                'data': {},
            },
        )
        mock_send_otp_token_sms.assert_called()
        _, kwargs = mock_send_otp_token_sms.call_args
        self.quick_offer.refresh_from_db()
        self.assertEqual(kwargs['phone_number'], self.quick_offer.phone_number)
        otp = kwargs['otp_token']
        response = self.client.post(
            f'/campaign/{self.quick_offer.code}/quick-offer-login',
            format='json',
            data={'otp': otp},
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Organization logged in successfully',
                'status': 200,
                'data': {
                    'auth_token': jwt_encode({'quick_offer_id': self.quick_offer.pk}),
                },
            },
        )


class CodeValidationViewTests(TestCase):
    def setUp(self):
        self.route = '/campaign/validate/{}'
        self.client = APIClient()

        self.organization = Organization.objects.create(
            name='name en',
            name_he='name he',
            manager_full_name='test',
            manager_phone_number='086786',
            manager_email='info@gmail.com',
        )
        self.campaign = Campaign.objects.create(
            organization=self.organization,
            name='campaign name',
            name_he='campaign name he',
            start_date_time=django_timezone.now(),
            end_date_time=django_timezone.now() + django_timezone.timedelta(hours=1),
            status=Campaign.CampaignStatusEnum.ACTIVE.name,
            login_page_title='en',
            login_page_title_he='he',
            login_page_subtitle='en',
            login_page_subtitle_he='he',
            main_page_first_banner_title='en',
            main_page_first_banner_title_he='he',
            main_page_first_banner_subtitle='en',
            main_page_first_banner_subtitle_he='he',
            main_page_first_banner_image='image',
            main_page_first_banner_mobile_image='mobile_image',
            main_page_second_banner_title='en',
            main_page_second_banner_title_he='he',
            main_page_second_banner_subtitle='en',
            main_page_second_banner_subtitle_he='he',
            main_page_second_banner_background_color='#123456',
            main_page_second_banner_text_color='WHITE',
            sms_sender_name='sender',
            sms_welcome_text='en',
            sms_welcome_text_he='he',
            email_welcome_text='en',
            email_welcome_text_he='he',
        )
        self.quick_offer = QuickOffer.objects.create(
            organization=self.organization,
            name='Test Quick Offer',
            code='TEST_QO',
            quick_offer_type=QuickOffer.TypeEnum.EVENT.name,
            ship_to=QuickOffer.ShippingEnum.TO_OFFICE.name,
            status=QuickOffer.StatusEnum.ACTIVE.name,
            login_page_title='Test Login Page',
            login_page_subtitle='Welcome to the Test Quick Offer!',
            main_page_first_banner_title='Welcome to Our Quick Offer',
            main_page_first_banner_subtitle='Check out our amazing offers!',
            main_page_first_banner_image='default-banner.png',
            main_page_first_banner_mobile_image='default-banner.png',
            main_page_second_banner_title='Special Deals',
            main_page_second_banner_subtitle='Don’t miss out!',
            main_page_second_banner_background_color='#C1E0CE',
            main_page_second_banner_text_color='BLACK',
            sms_sender_name='TestSender',
            sms_welcome_text='Welcome to the Quick Offer!',
            email_welcome_text='Thank you for choosing our Quick Offer!',
            auth_method=QuickOffer.AuthMethodEnum.EMAIL.name,
            auth_id='test_auth_id',
            phone_number='1234567890',
            email='test@example.com',
            nicklas_status=QuickOffer.NicklasStatusEnum.WAITING_TO_CLIENT.name,
            client_status=QuickOffer.ClientStatusEnum.READY_TO_CHECK.name,
            last_login=django_timezone.now(),
            otp_secret=None,
        )

    def test_valid_campaign_code(self):
        response = self.client.get(self.route.format(self.campaign.code))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Campaign code exists',
                'status': 200,
                'data': 'campaign_code',
            },
        )

    def test_valid_quick_offer_code(self):
        response = self.client.get(self.route.format(self.quick_offer.code))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Quick offer code exists',
                'status': 200,
                'data': 'quick_offer_code',
            },
        )

    def test_invalid_code(self):
        response = self.client.get(self.route.format('123'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Invalid Code',
                'status': 400,
                'data': 'invalid_code',
            },
        )


class QuickOfferProductsViewTestCase(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})

    def test_without_auth(self):
        response = self.client.get('/campaign/quick-offer-products')
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_query_param_category_id(self):
        products = self.quick_offer.products
        category_id = products.first().categories.first().id
        category_products = products.filter(categories=category_id)
        query_params = f'category_id={category_id}'
        response = self.client.get(
            '/campaign/quick-offer-products?' + query_params,
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertListEqual(
            [p['id'] for p in response.json()['data']['page_data']],
            list(category_products.values_list('id', flat=True)),
        )

    def test_query_param_limit(self):
        limit = 1
        query_params = f'limit={limit}'
        response = self.client.get(
            '/campaign/quick-offer-products?' + query_params,
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertListEqual(
            [p['id'] for p in response.json()['data']['page_data']],
            list(self.quick_offer.products.values_list('id', flat=True)[:limit]),
        )

    def test_query_param_page(self):
        limit = 2
        page = 2
        offset = (page - 1) * limit
        query_params = f'limit={limit}&page={page}'
        response = self.client.get(
            '/campaign/quick-offer-products?' + query_params,
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertListEqual(
            [p['id'] for p in response.json()['data']['page_data']],
            list(
                self.quick_offer.products.values_list('id', flat=True)[
                    offset : offset + limit
                ]
            ),
        )

    def test_query_param_search(self):
        product = self.quick_offer.products.first()
        for search in [product.name_en, product.name_he]:
            query_params = f'q={search}'
            response = self.client.get(
                '/campaign/quick-offer-products?' + query_params,
                HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            )
            self.assertEqual(response.status_code, 200)
            self.assertListEqual(
                [p['id'] for p in response.json()['data']['page_data']],
                list(
                    self.quick_offer.products.filter(
                        Q(name_en__icontains=search) | Q(name_he__icontains=search)
                    ).values_list('id', flat=True)
                ),
            )

    def test_query_param_not_including_tax(self):
        response = self.client.get(
            '/campaign/quick-offer-products?',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        tax_included_calculated_price = {
            p['id']: p['calculated_price'] for p in response.json()['data']['page_data']
        }
        query_params = 'including_tax=0'
        response = self.client.get(
            '/campaign/quick-offer-products?' + query_params,
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            all(
                int(p['calculated_price'])
                == int(
                    tax_included_calculated_price[p['id']] - int(settings.TAX_AMOUNT)
                )
                for p in response.json()['data']['page_data']
            )
        )

    def test_calculated_price_is_org_price(self):
        OrganizationProduct.objects.filter(
            organization=self.quick_offer.organization,
            product__in=self.quick_offer.products.all(),
        ).update(price=100)
        self.quick_offer.products.all().update(sale_price=None)
        response = self.client.get(
            '/campaign/quick-offer-products',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            all(
                p['calculated_price'] == 100
                for p in response.json()['data']['page_data']
            )
        )

    def test_calculated_price_is_product_sale_price(self):
        OrganizationProduct.objects.filter(
            organization=self.quick_offer.organization,
            product__in=self.quick_offer.products.all(),
        ).update(price=0)
        self.quick_offer.products.all().update(sale_price=110)
        response = self.client.get(
            '/campaign/quick-offer-products',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            all(
                p['calculated_price'] == 110
                for p in response.json()['data']['page_data']
            )
        )

    def test_order_by_calculated_price(self):
        expected_response_products = (
            OrganizationProduct.objects.filter(
                organization=self.quick_offer.organization,
                product__in=self.quick_offer.products.all(),
            )
            .order_by('price')
            .values_list('product_id', flat=True)
        )
        response = self.client.get(
            '/campaign/quick-offer-products',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertListEqual(
            [p['id'] for p in response.json()['data']['page_data']],
            list(expected_response_products),
        )

    def test_response_data(self):
        response = self.client.get(
            '/campaign/quick-offer-products?page=1&limit=1',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Quick offer products fetched successfully.',
                'status': 200,
                'data': {
                    'page_data': [
                        {
                            'id': 1,
                            'name': 'product name en 1',
                            'description': 'description 1',
                            'sku': 'sku 1',
                            'link': '',
                            'technical_details': '',
                            'warranty': '',
                            'exchange_value': None,
                            'exchange_policy': '',
                            'product_type': 'REGULAR',
                            'product_kind': 'PHYSICAL',
                            'brand': {'name': 'brand name en 1', 'logo_image': None},
                            'supplier': {'name': 'supplier name en 1'},
                            'images': [],
                            'categories': [
                                {
                                    'id': 1,
                                    'name': 'category1',
                                    'icon_image': None,
                                    'order': 1,
                                }
                            ],
                            'calculated_price': 100,
                            'remaining_quantity': 197,
                        },
                    ],
                    'page_num': 1,
                    'has_more': True,
                    'total_count': 3,
                },
            },
        )


class QuickOfferProductViewTestCase(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})
        self.product = self.quick_offer.products.first()

    def test_without_auth(self):
        response = self.client.get(f'/campaign/quick-offer-product/{self.product.id}')
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_inactive_quick_offer(self):
        QuickOffer.objects.update(status=QuickOffer.StatusEnum.PENDING.name)
        response = self.client.get(
            f'/campaign/quick-offer-product/{self.product.id}',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 403)
        self.assertDictEqual(
            response.json(),
            {'detail': 'You do not have permission to perform this action.'},
        )

    def test_invalid_product_id(self):
        response = self.client.get(
            f'/campaign/quick-offer-product/{Product.objects.count()+1}',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 404)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Product not found.',
                'status': 404,
                'code': 'not_found',
                'data': {},
            },
        )

    def test_valid_product_id(self):
        response = self.client.get(
            f'/campaign/quick-offer-product/{self.product.id}',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Product fetched successfully.',
                'status': 200,
                'data': QuickOfferProductSerializer(
                    self.product,
                    context={'quick_offer': self.quick_offer, 'tax_amount': 0},
                ).data,
            },
        )


class QuickOfferSelectProductsTestCase(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})

    def test_without_auth(self):
        response = self.client.post('/campaign/list/add_product')
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_inactive_quick_offer(self):
        QuickOffer.objects.update(status=QuickOffer.StatusEnum.PENDING.name)
        response = self.client.post(
            '/campaign/list/add_product',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 403)
        self.assertDictEqual(
            response.json(),
            {'detail': 'You do not have permission to perform this action.'},
        )

    def test_invalid_request_data(self):
        response = self.client.post(
            '/campaign/list/add_product',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            data={'product_id': 1},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_product_id(self):
        valid_product_ids = list(self.quick_offer.products.values_list('id', flat=True))
        invalid_product_id = list(
            Product.objects.exclude(id__in=valid_product_ids).values_list(
                'id', flat=True
            )
        )[0]
        response = self.client.post(
            '/campaign/list/add_product',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            data={'product_id': invalid_product_id, 'quantity': 1},
            format='json',
        )
        self.assertEqual(response.status_code, 404)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Product not found.',
                'code': 'not_found',
                'status': 404,
                'data': {},
            },
        )

    def test_valid_product_id(self):
        self.quick_offer.selected_products.clear()
        product_id = self.quick_offer.products.first().id
        response = self.client.post(
            '/campaign/list/add_product',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            data={'product_id': product_id, 'quantity': 5},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Product selected successfully with quantity.',
                'status': 200,
                'data': {},
            },
        )
        self.quick_offer.refresh_from_db()
        self.assertEqual(self.quick_offer.quickofferselectedproduct_set.count(), 1)
        self.assertEqual(
            self.quick_offer.quickofferselectedproduct_set.first().quantity, 5
        )
        response = self.client.post(
            '/campaign/list/add_product',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            data={'product_id': product_id, 'quantity': 2},
            format='json',
        )
        self.quick_offer.refresh_from_db()
        self.assertEqual(self.quick_offer.quickofferselectedproduct_set.count(), 1)
        self.assertEqual(
            self.quick_offer.quickofferselectedproduct_set.first().quantity, 2
        )


class GetQuickOfferSelectProductsTestCase(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.selected_quick_offer = QuickOfferSelectedProduct.objects.filter(
            quantity__gt=0
        ).all()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})

    def test_without_auth(self):
        response = self.client.get('/campaign/list/')
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_inactive_quick_offer(self):
        QuickOffer.objects.update(status=QuickOffer.StatusEnum.PENDING.name)
        response = self.client.get(
            '/campaign/list/',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 403)
        self.assertDictEqual(
            response.json(),
            {'detail': 'You do not have permission to perform this action.'},
        )

    def test_valid_quick_offer_product(self):
        response = self.client.get(
            '/campaign/list/',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        serialized_data = QuickOfferSelectProductsDetailSerializer(
            self.selected_quick_offer,
            many=True,
            context={
                'quick_offer': self.quick_offer,
            },
        ).data

        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Selected Product fetched successfully.',
                'status': 200,
                'data': {
                    'products': serialized_data,
                },
            },
        )

class QuickOfferShareTestCase(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})

    def test_without_auth(self):
        response = self.client.post('/campaign/quick-offer-share/')
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_inactive_quick_offer(self):
        QuickOffer.objects.update(status=QuickOffer.StatusEnum.PENDING.name)
        response = self.client.post(
            '/campaign/quick-offer-share/',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 403)
        self.assertDictEqual(
            response.json(),
            {'detail': 'You do not have permission to perform this action.'},
        )

    def test_invalid_request_data(self):
        response = self.client.post(
            '/campaign/quick-offer-share/',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            data={'share_type': 'Cart'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_share_type(self):
        response = self.client.post(
            '/campaign/quick-offer-share/',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            data={'share_type': 'Event', 'product_ids': [1, 2]},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Invalid share type provided.',
                'code': 'invalid_share_type',
                'status': 400,
            },
        )

    def test_not_selected_quick_offer(self):
        quick_offer = QuickOffer.objects.filter(id=2).first()
        auth_token = jwt_encode({'quick_offer_id': quick_offer.id})
        response = self.client.post(
            '/campaign/quick-offer-share/',
            HTTP_X_AUTHORIZATION=f'Bearer {auth_token}',
            data={'share_type': 'Cart', 'product_ids': [1, 2]},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'No Products Selected.',
                'code': 'no_products_selected',
                'status': 400,
            },
        )

    def test_valid_product_id(self):
        response = self.client.post(
            '/campaign/quick-offer-share/',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            data={'share_type': 'Cart', 'product_ids': [1, 2]},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        share = Share.objects.first()
        share.refresh_from_db()
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Products shared successfully.',
                'status': 200,
                'data': {'share_id': str(share.share_id)},
            },
        )

class GetQuickOfferShareTestCase(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})
        self.share1 = Share.objects.create(
            share_type='Cart', quick_offer=self.quick_offer
        )

    def test_invalid_share_id(self):
        response = self.client.get(
            '/campaign/get-quick-offer-share/aaa78629-2013-4389-996a-b90955fb796a'
        )
        self.assertEqual(response.status_code, 404)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Share not found.',
                'code': 'not_found',
                'status': 404,
            },
        )

    def test_valid_share_id(self):
        response = self.client.get(
            f'/campaign/get-quick-offer-share/{self.share1.share_id}',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)

        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Share details fetched successfully.',
                'status': 200,
                'data': {
                    'share_type': 'Cart',
                    'products': [],
                    'cart': [
                        {
                            'id': 1,
                            'product': {
                                'id': 1,
                                'name': 'product name en 1',
                                'description': 'description 1',
                                'sku': 'sku 1',
                                'link': '',
                                'technical_details': '',
                                'warranty': '',
                                'exchange_value': None,
                                'exchange_policy': '',
                                'product_type': 'REGULAR',
                                'product_kind': 'PHYSICAL',
                                'brand': {
                                    'name': 'brand name en 1',
                                    'logo_image': None,
                                },
                                'supplier': {'name': 'supplier name en 1'},
                                'images': [],
                                'categories': [
                                    {
                                        'id': 1,
                                        'name': 'category1',
                                        'icon_image': None,
                                        'order': 1,
                                    }
                                ],
                                'calculated_price': 100,
                                'remaining_quantity': 197,
                            },
                            'quantity': 2,
                        },
                        {
                            'id': 2,
                            'product': {
                                'id': 2,
                                'name': 'product name en 2',
                                'description': 'description 1',
                                'sku': 'sku 2',
                                'link': '',
                                'technical_details': '',
                                'warranty': '',
                                'exchange_value': None,
                                'exchange_policy': '',
                                'product_type': 'REGULAR',
                                'product_kind': 'PHYSICAL',
                                'brand': {
                                    'name': 'brand name en 1',
                                    'logo_image': None,
                                },
                                'supplier': {'name': 'supplier name en 1'},
                                'images': [],
                                'categories': [
                                    {
                                        'id': 2,
                                        'name': 'category2',
                                        'icon_image': None,
                                        'order': 2,
                                    }
                                ],
                                'calculated_price': 110,
                                'remaining_quantity': 200,
                            },
                            'quantity': 0,
                        },
                    ],
                },
            },
        )

class QuickOfferCreateOrder(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})
        order = Order.objects.create(
            campaign_employee_id=CampaignEmployee.objects.first(),
            order_date_time=datetime.now(timezone.utc),
            cost_from_budget=10,
            cost_added=10,
        )
        for i in range(1, 3):
            OrderProduct.objects.create(
                order_id=order,
                product_id=EmployeeGroupCampaignProduct.objects.get(pk=1),
                quantity=10 * i,
            )
            OrderProduct.objects.create(
                order_id=order,
                product_id=EmployeeGroupCampaignProduct.objects.get(pk=2),
                quantity=20 * i,
            )

    def test_without_auth(self):
        response = self.client.post('/campaign/quick-offer-order')
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_inactive_quick_offer(self):
        QuickOffer.objects.update(status=QuickOffer.StatusEnum.PENDING.name)
        response = self.client.post(
            '/campaign/quick-offer-order',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 403)
        self.assertDictEqual(
            response.json(),
            {'detail': 'You do not have permission to perform this action.'},
        )

    def test_request_fields(self):
        fields = [
            'full_name',
            'phone_number',
            'additional_phone_number',
            'delivery_city',
            'delivery_street',
            'delivery_street_number',
            'delivery_apartment_number',
            'delivery_additional_details',
            'country',
            'state_code',
            'zip_code',
            'size',
            'color',
        ]
        response = self.client.post(
            '/campaign/quick-offer-order',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            format='json',
            data={f: [] for f in fields},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                'success': False,
                'message': 'Request is invalid.',
                'code': 'request_invalid',
                'status': 400,
                'data': {f: ['Not a valid string.'] for f in fields},
            },
        )

    def test_selected_products_not_found(self):
        QuickOfferSelectedProduct.objects.all().delete()
        response = self.client.post(
            '/campaign/quick-offer-order',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 404)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Empty cart.',
                'code': 'not_found',
                'status': 404,
                'data': {},
            },
        )

    def test_selected_products_quantity_more_than_product_remaining_quantity(self):
        QuickOfferSelectedProduct.objects.filter(pk=1).update(quantity=200)
        QuickOfferSelectedProduct.objects.filter(pk=2).update(quantity=300)
        response = self.client.post(
            '/campaign/quick-offer-order',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 400)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': (
                    'The requested quantity is not available. '
                    'The remaining quantity is 167.'
                ),
                'code': 'request_invalid',
                'status': 400,
                'data': {},
            },
        )

    def test_existing_pending_order(self):
        QuickOfferOrder.objects.update(status=QuickOfferOrder.OrderStatusEnum.PENDING)
        response = self.client.post(
            '/campaign/quick-offer-order',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 400)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Quick Offer already ordered.',
                'code': 'already_ordered',
                'status': 400,
                'data': {},
            },
        )

    def test_valid_create_order(self):
        QuickOfferOrder.objects.all().delete()
        self.assertFalse(QuickOfferOrder.objects.all().count())
        self.assertFalse(QuickOfferOrderProduct.objects.all().count())
        request_data = {
            'full_name': 'full_name',
            'phone_number': 'phone_number',
            'additional_phone_number': 'additional_phone_number',
            'delivery_city': 'delivery_city',
            'delivery_street': 'delivery_street',
            'delivery_street_number': 'delivery_street_number',
            'delivery_apartment_number': 'delivery_apartment_number',
            'delivery_additional_details': 'delivery_additional_details',
            'country': 'country',
            'state_code': 'state_code',
            'zip_code': 'zip_code',
            'size': 'size',
            'color': 'color',
        }
        response = self.client.post(
            '/campaign/quick-offer-order',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
            format='json',
            data=request_data,
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'Order placed successfully.',
                'status': 200,
                'data': {'reference': 2},
            },
        )
        quick_offer_order = QuickOfferOrder.objects.filter(reference=2).first()
        self.assertTrue(quick_offer_order)
        self.assertTrue(
            QuickOfferOrderProduct.objects.filter(quick_offer_order=quick_offer_order)
        )


class QuickOfferGetOrder(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})

    def test_without_auth(self):
        response = self.client.get('/campaign/quick-offer-order')
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_inactive_quick_offer(self):
        QuickOffer.objects.update(status=QuickOffer.StatusEnum.PENDING)
        response = self.client.get(
            '/campaign/quick-offer-order',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 403)
        self.assertDictEqual(
            response.json(),
            {'detail': 'You do not have permission to perform this action.'},
        )

    def test_order_not_found(self):
        QuickOfferOrder.objects.update(
            status=QuickOfferOrder.OrderStatusEnum.INCOMPLETE
        )
        response = self.client.get(
            '/campaign/quick-offer-order',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 404)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Order not found.',
                'code': 'not_found',
                'status': 404,
                'data': {},
            },
        )

    def test_valid_request(self):
        QuickOfferOrder.objects.update(status=QuickOfferOrder.OrderStatusEnum.PENDING)
        response = self.client.get(
            '/campaign/quick-offer-order',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        response.json()['data'].pop('order_date_time')
        self.assertEqual(
            response.json(),
            {
                'success': True,
                'message': 'Quick offer order fetched successfully.',
                'status': 200,
                'data': {
                    'full_name': 'quick_offer_order_1',
                    'reference': 1,
                    'products': [
                        {
                            'quantity': 3,
                            'product': {
                                'id': 1,
                                'name': 'product name en 1',
                                'description': 'description 1',
                                'sku': 'sku 1',
                                'link': '',
                                'technical_details': '',
                                'warranty': '',
                                'exchange_value': None,
                                'exchange_policy': '',
                                'product_type': 'REGULAR',
                                'product_kind': 'PHYSICAL',
                                'brand': {
                                    'name': 'brand name en 1',
                                    'logo_image': None,
                                },
                                'supplier': {'name': 'supplier name en 1'},
                                'images': [],
                                'categories': [
                                    {
                                        'id': 1,
                                        'name': 'category1',
                                        'icon_image': None,
                                        'order': 1,
                                    }
                                ],
                                'calculated_price': 100,
                                'remaining_quantity': 197,
                            },
                            'total_cost': 3,
                        }
                    ],
                    'phone_number': '9876543210',
                    'additional_phone_number': '9876543210',
                    'delivery_city': 'quick_offer_order_1',
                    'delivery_street': 'quick_offer_order_1',
                    'delivery_street_number': 'quick_offer_order_1',
                    'delivery_apartment_number': 'quick_offer_order_1',
                    'delivery_additional_details': 'quick_offer_order_1',
                },
            },
        )


class QuickOfferCancelOrder(TestCase):
    fixtures = [
        'src/fixtures/inventory.json',
        'src/fixtures/campaign.json',
        'src/fixtures/quick_offers.json',
    ]

    def setUp(self):
        self.client = APIClient()
        self.quick_offer = QuickOffer.objects.first()
        self.auth_token = jwt_encode({'quick_offer_id': self.quick_offer.id})
        self.quick_offer_order = QuickOfferOrder.objects.first()

    def test_without_auth(self):
        response = self.client.put(
            f'/campaign/quick-offer-cancel-order/{self.quick_offer_order.pk}'
        )
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(
            response.json(),
            {'detail': 'Authentication credentials were not provided.'},
        )

    def test_inactive_quick_offer(self):
        QuickOffer.objects.update(status=QuickOffer.StatusEnum.PENDING)
        response = self.client.put(
            f'/campaign/quick-offer-cancel-order/{self.quick_offer_order.pk}',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 403)
        self.assertDictEqual(
            response.json(),
            {'detail': 'You do not have permission to perform this action.'},
        )

    def test_order_not_found(self):
        QuickOfferOrder.objects.update(
            status=QuickOfferOrder.OrderStatusEnum.INCOMPLETE
        )
        response = self.client.put(
            f'/campaign/quick-offer-cancel-order/{self.quick_offer_order.pk}',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 404)
        self.assertDictEqual(
            response.json(),
            {
                'success': False,
                'message': 'Order not found.',
                'code': 'not_found',
                'status': 404,
                'data': {},
            },
        )

    def test_valid_request(self):
        QuickOfferOrder.objects.update(status=QuickOfferOrder.OrderStatusEnum.PENDING)
        self.assertTrue(
            QuickOfferSelectedProduct.objects.filter(quick_offer=self.quick_offer)
        )
        response = self.client.put(
            f'/campaign/quick-offer-cancel-order/{self.quick_offer_order.pk}',
            HTTP_X_AUTHORIZATION=f'Bearer {self.auth_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                'success': True,
                'message': 'order canceled successfully.',
                'status': 200,
                'data': {},
            },
        )
        self.quick_offer_order.refresh_from_db()
        self.assertEqual(self.quick_offer_order.status, 'OrderStatusEnum.CANCELLED')
        self.assertFalse(
            QuickOfferSelectedProduct.objects.filter(quick_offer=self.quick_offer)
        )
