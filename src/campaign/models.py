from enum import Enum
import secrets
import string

from colorfield.fields import ColorField
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.db import models
from django.db.models.functions import Cast, Concat, Left
from django.urls import reverse
import pyotp

from lib.admin_utils import anchor_tag_popup
from lib.phone_utils import convert_phone_number_to_long_form, validate_phone_number
from lib.storage import RandomNameImageField

from .constants import LANGUAGE_CHOICES


UserModel = get_user_model()


class Organization(models.Model):
    name = models.CharField(max_length=255)
    manager_full_name = models.CharField(max_length=255)
    manager_phone_number = models.CharField(
        max_length=255, validators=[validate_phone_number]
    )
    manager_email = models.CharField(max_length=255, validators=[validate_email])
    logo_image = RandomNameImageField(null=False, blank=False)
    products = models.ManyToManyField(
        'inventory.Product', through='OrganizationProduct'
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.manager_phone_number:
            formatted_phone_number = convert_phone_number_to_long_form(
                self.manager_phone_number
            )

            if formatted_phone_number:
                self.manager_phone_number = formatted_phone_number
            else:
                raise Exception(f'Invalid phone number: {self.manager_phone_number}')

        return super().save(*args, **kwargs)


class OrganizationProduct(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    product = models.ForeignKey('inventory.Product', on_delete=models.CASCADE)
    price = models.IntegerField()


class Employee(models.Model):
    employee_group = models.ForeignKey('EmployeeGroup', on_delete=models.CASCADE)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    auth_id = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    phone_number = models.CharField(
        max_length=255, null=True, blank=True, validators=[validate_phone_number]
    )
    birthday_date = models.DateField(null=True, blank=True)
    default_language = models.CharField(
        max_length=255, choices=LANGUAGE_CHOICES, default='HE'
    )
    delivery_city = models.CharField(max_length=255, null=True, blank=True)
    delivery_street = models.CharField(max_length=255, null=True, blank=True)
    delivery_street_number = models.CharField(max_length=255, null=True, blank=True)
    delivery_apartment_number = models.CharField(max_length=255, null=True, blank=True)
    active = models.BooleanField(default=True)
    otp_secret = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        if self.phone_number:
            formatted_phone_number = convert_phone_number_to_long_form(
                self.phone_number
            )

            if formatted_phone_number:
                self.phone_number = formatted_phone_number
            else:
                raise Exception(f'Invalid phone number: {self.phone_number}')

        return super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    def generate_otp(self):
        try:
            self.otp_secret = pyotp.random_base32()
            self.save()
            return pyotp.TOTP(self.otp_secret, interval=settings.OTP_INTERVAL).now()
        except Exception:
            return None

    def verify_otp(self, otp: str):
        try:
            return pyotp.TOTP(self.otp_secret, interval=settings.OTP_INTERVAL).verify(
                otp
            )
        except Exception:
            return False

    @admin.display(description='Organization')
    def organization(self):
        return self.employee_group.organization


class BannerTextColorEnum(Enum):
    BLACK = 'Black'
    WHITE = 'White'


class Campaign(models.Model):
    class CampaignTypeEnum(Enum):
        EVENT = 'Event'

    class CampaignShippingEnum(Enum):
        TO_OFFICE = 'To Office'
        TO_EMPLOYEES = 'To Employees'

    class CampaignStatusEnum(Enum):
        PENDING = 'Pending'
        OFFER = 'Offer'
        ACTIVE = 'Active'
        FINISHED = 'Finished'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    start_date_time = models.DateTimeField()
    end_date_time = models.DateTimeField()
    code = models.CharField(max_length=255)
    employees = models.ManyToManyField(Employee, through='CampaignEmployee')
    campaign_type = models.CharField(
        max_length=30,
        choices=[
            (campaign_type.name, campaign_type.value)
            for campaign_type in CampaignTypeEnum
        ],
        default=CampaignTypeEnum.EVENT,
    )
    ship_to = models.CharField(
        max_length=30,
        choices=[
            (campaign_shipping.name, campaign_shipping.value)
            for campaign_shipping in CampaignShippingEnum
        ],
        default=CampaignShippingEnum.TO_OFFICE,
    )
    status = models.CharField(
        max_length=30,
        choices=[
            (campaign_status.name, campaign_status.value)
            for campaign_status in CampaignStatusEnum
        ],
        default=CampaignStatusEnum.PENDING.name,
    )
    login_page_title = models.CharField(max_length=255)
    login_page_subtitle = models.TextField()
    main_page_first_banner_title = models.CharField(
        max_length=255, null=True, blank=True
    )
    main_page_first_banner_subtitle = models.TextField(null=True, blank=True)
    main_page_first_banner_image = RandomNameImageField()
    main_page_first_banner_mobile_image = RandomNameImageField()
    main_page_second_banner_title = models.CharField(
        max_length=255, null=True, blank=True
    )
    main_page_second_banner_subtitle = models.TextField(null=True, blank=True)
    main_page_second_banner_background_color = ColorField(default='#C1E0CE')
    main_page_second_banner_text_color = models.CharField(
        max_length=30,
        choices=[
            (banner_text_color.name, banner_text_color.value)
            for banner_text_color in BannerTextColorEnum
        ],
    )
    sms_sender_name = models.CharField(max_length=11)
    sms_welcome_text = models.TextField()
    email_welcome_text = models.TextField()
    login_page_image = RandomNameImageField(null=True, blank=True)
    login_page_mobile_image = RandomNameImageField(null=True, blank=True)

    @property
    def is_active(self):
        # is active is currently based on the status and NOT the start abd end
        # dates
        return self.status == Campaign.CampaignStatusEnum.ACTIVE.name

    @property
    def total_employees(self):
        return CampaignEmployee.objects.filter(campaign=self).count()

    @property
    def organization_link(self):
        find_organization = EmployeeGroupCampaign.objects.filter(campaign=self).first()
        if find_organization:
            return anchor_tag_popup(
                reverse(
                    'admin:campaign_organization_change', args=[find_organization.pk]
                ),
                find_organization.employee_group.organization.name,
            )
        return None

    @admin.display(description='Ordered #')
    def ordered_number(self):
        return (
            Order.objects.filter(
                campaign_employee_id__campaign=self,
                status=Order.OrderStatusEnum.PENDING.name,
            )
            .values_list('campaign_employee_id__employee', flat=True)
            .distinct()
            .count()
        )

    @admin.display(description='Ordered %')
    def ordered_percentage(self):
        return (self.ordered_number() / (self.total_employees or 1)) * 100

    def __str__(self):
        return self.name


class CampaignEmployee(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    first_login = models.DateTimeField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [['campaign', 'employee']]

    def __str__(self):
        return f'{self.employee.full_name} | {self.campaign.name}'


class EmployeeAuthEnum(Enum):
    EMAIL = 'email'
    SMS = 'sms'
    AUTH_ID = 'auth_id'


class DeliveryLocationEnum(Enum):
    ToHome = 'to home'
    ToOffice = 'to office'


class EmployeeGroup(models.Model):
    name = models.CharField(max_length=255)
    campaigns = models.ManyToManyField(Campaign, through='EmployeeGroupCampaign')
    organization = models.ForeignKey(
        Organization, on_delete=models.SET_NULL, null=True, blank=True
    )
    delivery_city = models.CharField(max_length=255, null=True, blank=True)
    delivery_street = models.CharField(max_length=255, null=True, blank=True)
    delivery_street_number = models.CharField(max_length=255, null=True, blank=True)
    delivery_apartment_number = models.CharField(max_length=255, null=True, blank=True)
    delivery_location = models.CharField(
        max_length=50,
        default=DeliveryLocationEnum.ToOffice,
        choices=[(location.name, location.value) for location in DeliveryLocationEnum],
    )
    auth_method = models.CharField(
        max_length=50,
        default=EmployeeAuthEnum.EMAIL.name,
        choices=[(auth_type.name, auth_type.value) for auth_type in EmployeeAuthEnum],
    )

    def __str__(self):
        return self.name

    @property
    def campaign_names(self):
        return ', '.join(
            self.employeegroupcampaign_set.filter(
                campaign__status='ACTIVE'
            ).values_list('campaign__name', flat=True)
        )

    @property
    def total_employees(self):
        return Employee.objects.filter(employee_group=self).count()


class EmployeeGroupCampaign(models.Model):
    class ProductSelectionTypeEnum(Enum):
        SINGLE = 'Single'
        MULTIPLE = 'Multiple'

    class CurrencyTypeEnum(Enum):
        COINS = 'Coins'
        CURRENCY = 'Currency'

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    employee_group = models.ForeignKey(EmployeeGroup, on_delete=models.CASCADE)
    budget_per_employee = models.IntegerField()
    product_selection_mode = models.CharField(
        max_length=32,
        default=ProductSelectionTypeEnum.SINGLE.name,
        choices=[
            (productSelection.name, productSelection.value)
            for productSelection in ProductSelectionTypeEnum
        ],
    )
    displayed_currency = models.CharField(
        max_length=32,
        default=CurrencyTypeEnum.CURRENCY.name,
        choices=[(currency.name, currency.value) for currency in CurrencyTypeEnum],
    )

    @property
    def employee_site_link(self):
        # suffix indicates the authentication method employees need to use
        suffix = 'e'
        if self.employee_group.auth_method == EmployeeAuthEnum.SMS.name:
            suffix = 'p'
        elif self.employee_group.auth_method == EmployeeAuthEnum.AUTH_ID.name:
            suffix = 'a'

        return f'{settings.EMPLOYEE_SITE_BASE_URL}/{self.campaign.code}/{suffix}'


class EmployeeGroupCampaignProduct(models.Model):
    employee_group_campaign_id = models.ForeignKey(
        EmployeeGroupCampaign, on_delete=models.CASCADE
    )
    product_id = models.ForeignKey('inventory.Product', on_delete=models.CASCADE)

    def __str__(self):
        return self.product_id.name


class Cart(models.Model):
    campaign_employee_id = models.ForeignKey(CampaignEmployee, on_delete=models.CASCADE)


class CartProduct(models.Model):
    cart_id = models.ForeignKey(Cart, on_delete=models.CASCADE)
    product_id = models.ForeignKey(
        EmployeeGroupCampaignProduct, on_delete=models.CASCADE
    )
    quantity = models.IntegerField()

    @property
    def product(self):
        return self.product_id.product_id


class OrderManager(models.Manager):
    def get_queryset(self):
        return (
            super(OrderManager, self)
            .get_queryset()
            .select_related(
                'campaign_employee_id',
                'campaign_employee_id__campaign',
                'campaign_employee_id__campaign__organization',
            )
            .annotate(
                order_id=Concat(
                    Left('campaign_employee_id__campaign__organization__name_en', 10),
                    models.Value('_'),
                    Cast('reference', output_field=models.CharField()),
                )
            )
        )


class Order(models.Model):
    class OrderStatusEnum(Enum):
        INCOMPLETE = 'Incomplete'
        PENDING = 'Pending'
        CANCELLED = 'Cancelled'
        SENT_TO_LOGISTIC_CENTER = 'Sent To Logistic Center'

    reference = models.AutoField(primary_key=True)
    campaign_employee_id = models.ForeignKey(CampaignEmployee, on_delete=models.CASCADE)
    order_date_time = models.DateTimeField()
    cost_from_budget = models.IntegerField()
    cost_added = models.IntegerField()
    status = models.CharField(
        max_length=50,
        default=OrderStatusEnum.INCOMPLETE,
        choices=[(status.name, status.value) for status in OrderStatusEnum],
    )
    full_name = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(
        max_length=255, null=True, blank=True, validators=[validate_phone_number]
    )
    additional_phone_number = models.CharField(
        max_length=255, null=True, blank=True, validators=[validate_phone_number]
    )
    delivery_city = models.CharField(max_length=255, null=True, blank=True)
    delivery_street = models.CharField(max_length=255, null=True, blank=True)
    delivery_street_number = models.CharField(max_length=255, null=True, blank=True)
    delivery_apartment_number = models.CharField(max_length=255, null=True, blank=True)
    delivery_additional_details = models.CharField(
        max_length=512, null=True, blank=True
    )
    impersonated_by = models.ForeignKey(
        UserModel, on_delete=models.SET_NULL, null=True, blank=True
    )
    logistics_center_status = models.CharField(max_length=16, null=True, blank=True)

    # override the model manager so we can use `order_id` field for filters
    # and calculate the value in one central place
    objects = OrderManager()

    def __str__(self):
        return f'Order #{self.reference}'

    @admin.display(description='Organization')
    def organization(self):
        return self.campaign_employee_id.campaign.organization.name

    @admin.display(description='Campaign')
    def campaign(self):
        return self.campaign_employee_id.campaign.name

    @admin.display(description='Employee')
    def employee_name(self):
        return self.campaign_employee_id.employee.full_name

    @admin.display(description='Products')
    def ordered_product_names(self):
        return ', '.join(
            [p.product_id.product_id.name for p in self.orderproduct_set.all()]
        )

    @admin.display(description='Product Types')
    def ordered_product_types(self):
        return ', '.join(
            [p.product_id.product_id.product_type for p in self.orderproduct_set.all()]
        )

    @admin.display(description='Product Kinds')
    def ordered_product_kinds(self):
        return ', '.join(
            [p.product_id.product_id.product_kind for p in self.orderproduct_set.all()]
        )


class OrderProduct(models.Model):
    order_id = models.ForeignKey(Order, on_delete=models.CASCADE)
    product_id = models.ForeignKey(
        EmployeeGroupCampaignProduct, on_delete=models.CASCADE
    )
    quantity = models.IntegerField()

    @property
    def product(self):
        return self.product_id.product_id


class CampaignImpersonationToken(models.Model):
    token = models.TextField(db_index=True, unique=True)
    valid_until_epoch_seconds = models.BigIntegerField()
    used = models.BooleanField(default=False)
    user = models.ForeignKey(UserModel, on_delete=models.SET_NULL, null=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True)
    employee_group_campaign = models.ForeignKey(
        EmployeeGroupCampaign, on_delete=models.SET_NULL, null=True
    )
    campaign_employee = models.ForeignKey(
        CampaignEmployee, on_delete=models.SET_NULL, null=True
    )

    def _generate_token(self):
        letters = string.ascii_letters + string.digits + string.punctuation
        return ''.join(secrets.choice(letters) for _ in range(256))

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self._generate_token()

        return super().save(*args, **kwargs)
