import re
from typing import Optional

from django.conf import settings
from django.db.models import Prefetch
from django.utils.translation import gettext
from rest_framework import serializers

from campaign.constants import SPECIAL_OFFER_ENUM_TRANSLATIONS
from campaign.models import (
    Campaign,
    Cart,
    CartProduct,
    DeliveryLocationEnum,
    Employee,
    EmployeeGroup,
    EmployeeGroupCampaign,
    EmployeeGroupCampaignProduct,
    Order,
    OrderProduct,
    Organization,
    OrganizationProduct,
    QuickOffer,
    QuickOfferProduct,
    QuickOfferSelectedProduct,
    QuickOfferTag,
)
from campaign.utils import (
    get_campaign_product_price,
    get_quick_offer_product_price,
    price_deduct_tax,
    transform_variations,
)
from inventory.models import (
    Brand,
    Category,
    ColorVariation,
    Product,
    ProductImage,
    Supplier,
    Tag,
    TextVariation,
    Variation,
)
from lib.phone_utils import convert_phone_number_to_long_form


class LangSerializer(serializers.Serializer):
    lang = serializers.ChoiceField(
        choices=settings.MODELTRANSLATION_LANGUAGES,
        required=False,
        error_messages={
            'invalid_choice': (
                'Provided choice is invalid. '
                f'Available choices are: {settings.MODELTRANSLATION_LANGUAGES}'
            )
        },
    )


class TranslationSerializer(serializers.ModelSerializer):
    def get_field_names(self, declared_fields, info):
        fields = super().get_field_names(declared_fields, info)
        try:
            langs = settings.MODELTRANSLATION_LANGUAGES
            fields = [
                field
                for field in fields
                if not any(re.search(rf'(.+)_{lang}', field) for lang in langs)
            ]
        except Exception:
            ...
        return fields


class DynamicFieldsSerializer(TranslationSerializer):
    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        fields = kwargs.pop('fields', None)
        # Instantiate the superclass normally
        super().__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)


class EmployeeGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeGroup
        fields = '__all__'


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    employee_group = EmployeeGroupSerializer(read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id',
            'first_name',
            'last_name',
            'auth_id',
            'email',
            'phone_number',
            'birthday_date',
            'default_language',
            'delivery_city',
            'delivery_street',
            'delivery_street_number',
            'delivery_apartment_number',
            'active',
            'otp_secret',
            'full_name',
            'employee_group',
        ]

    def get_full_name(self, obj):
        return obj.full_name


class EmployeeReportSerializer(serializers.ModelSerializer):
    employee_group = EmployeeGroupSerializer(read_only=True)

    class Meta:
        model = Employee
        fields = [
            'first_name_he',
            'last_name_he',
            'email',
            'phone_number',
            'employee_group',
        ]


class CampaignSerializer(serializers.ModelSerializer):
    organization_name = serializers.SerializerMethodField()
    organization_logo_image = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = (
            'name',
            'code',
            'is_active',
            'organization_name',
            'organization_logo_image',
            'login_page_title',
            'login_page_subtitle',
            'login_page_image',
            'login_page_mobile_image',
            'campaign_type',
        )

    def get_organization_name(self, obj):
        if obj.organization:
            return obj.organization.name
        return None

    def get_organization_logo_image(self, obj):
        if obj.organization and obj.organization.logo_image:
            return obj.organization.logo_image.url
        return None


class CampaignExtendedSerializer(CampaignSerializer):
    delivery_location = serializers.SerializerMethodField()
    office_delivery_address = serializers.SerializerMethodField()
    product_selection_mode = serializers.SerializerMethodField()
    displayed_currency = serializers.SerializerMethodField()
    budget_per_employee = serializers.SerializerMethodField()
    employee_order_reference = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    check_out_location = serializers.SerializerMethodField()

    class Meta(CampaignSerializer.Meta):
        existing_fields = CampaignSerializer.Meta.fields
        fields_list = list(existing_fields)
        fields_list.extend(
            [
                'main_page_first_banner_title',
                'main_page_first_banner_subtitle',
                'main_page_first_banner_image',
                'main_page_first_banner_mobile_image',
                'main_page_second_banner_title',
                'main_page_second_banner_subtitle',
                'main_page_second_banner_background_color',
                'main_page_second_banner_text_color',
                'delivery_location',
                'office_delivery_address',
                'product_selection_mode',
                'displayed_currency',
                'budget_per_employee',
                'employee_order_reference',
                'employee_name',
                'check_out_location',
                'campaign_type',
            ]
        )
        fields = fields_list

    def get_delivery_location(self, obj):
        return self.context['employee'].employee_group.delivery_location

    def get_office_delivery_address(self, obj):
        employee_group = self.context['employee'].employee_group

        if employee_group.delivery_location == DeliveryLocationEnum.ToOffice.name:
            return ', '.join(
                [
                    address_part
                    for address_part in [
                        (
                            f'{employee_group.delivery_street} '
                            f'{employee_group.delivery_street_number}'
                        ),
                        employee_group.delivery_apartment_number,
                        employee_group.delivery_city,
                    ]
                    if address_part
                ]
            )
        else:
            return None

    def get_product_selection_mode(self, obj):
        return self.context['employee_group_campaign'].product_selection_mode

    def get_displayed_currency(self, obj):
        return self.context['employee_group_campaign'].displayed_currency

    def get_budget_per_employee(self, obj):
        left_budget = self.get_left_budget(obj=obj)
        if left_budget == 0:
            return 0
        return (
            self.get_left_budget(obj=obj)
            or self.context['employee_group_campaign'].budget_per_employee
        )

    def get_employee_order_reference(self, obj):
        if self.context['existing_order']:
            return self.context['existing_order'].reference
        else:
            return None

    def get_employee_name(self, obj):
        return self.context['employee'].full_name

    def get_check_out_location(self, obj):
        return self.context['employee_group_campaign'].check_out_location

    def get_total_budget(self, obj):
        employee = self.context['employee']
        return employee.total_budget_campaign(campaign=obj)

    def get_left_budget(self, obj):
        employee = self.context['employee']
        return employee.get_left_budget_campaign(campaign=obj)


class BrandSerializer(TranslationSerializer):
    class Meta:
        model = Brand
        fields = [
            'name',
            'logo_image',
        ]


class SupplierSerializer(TranslationSerializer):
    class Meta:
        model = Supplier
        fields = ['name']


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = [
            'main',
            'image',
        ]


class CategorySerializer(TranslationSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class TagSerializer(TranslationSerializer):
    class Meta:
        model = Tag
        fields = '__all__'


class EmployeeGroupCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeGroupCampaign
        fields = '__all__'


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['name', 'logo_image']

    def get_field_names(self, declared_fields, info):
        context_field_names = self.context.get('field_names', None)
        if context_field_names:
            return context_field_names
        return super().get_field_names(declared_fields, info)


class OrganizationProductSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = OrganizationProduct
        fields = ['organization', 'price']


class MoneyProductSerializerCampaignAdmin(DynamicFieldsSerializer):
    employee_group = serializers.SerializerMethodField(read_only=True)
    organization_price = serializers.SerializerMethodField(read_only=True)
    voucher_value = serializers.SerializerMethodField(read_only=True)
    profit = serializers.SerializerMethodField(read_only=True)
    discount_to = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'name',
            'voucher_type',
            'employee_group',
            'supplier_discount_rate',
            'client_discount_rate',
            'organization_price',
            'voucher_value',
            'profit',
            'discount_to',
        ]

    def get_employee_group(self, obj: Product):
        return (
            EmployeeGroupCampaignProduct.objects.filter(
                product_id=obj,
                employee_group_campaign_id__campaign=self.context.get('campaign'),
            )
            .first()
            .employee_group_campaign_id.employee_group.name
        )

    def get_organization_price(self, obj: Product):
        return get_campaign_product_price(self.context.get('campaign'), obj)

    def get_voucher_value(self, obj: Product):
        employee = self.context.get('employee')
        campaign = self.context.get('campaign')
        if employee and campaign and obj.product_kind == 'MONEY':
            product: EmployeeGroupCampaignProduct = (
                EmployeeGroupCampaignProduct.objects.get(
                    employee_group_campaign_id__campaign=campaign,
                    employee_group_campaign_id__employee_group=employee,
                    product_id=obj,
                )
            )

            if product:
                budget = product.employee_group_campaign_id.budget_per_employee or 0
                if product.organization_discount_rate:
                    return round(
                        budget / (1 - (product.organization_discount_rate / 100)), 1
                    )
                else:
                    return budget
        return 0

    def get_profit(self, obj: Product):
        profit = self.get_organization_price(obj=obj) - obj.total_cost
        return profit if profit else 0

    def get_discount_to(self, obj: Product):
        employee = self.context.get('employee')
        if employee:
            product: EmployeeGroupCampaignProduct = (
                EmployeeGroupCampaignProduct.objects.filter(
                    employee_group_campaign_id__campaign=self.context['campaign'],
                    employee_group_campaign_id__employee_group=employee,
                    product_id=obj,
                ).first()
            )
        else:
            product: EmployeeGroupCampaignProduct = (
                EmployeeGroupCampaignProduct.objects.filter(
                    employee_group_campaign_id__campaign=self.context['campaign'],
                    product_id=obj,
                ).first()
            )

        return product.discount_mode if product else ''


class PhysicalProductSerializerCampaignAdmin(DynamicFieldsSerializer):
    supplier_name = serializers.SerializerMethodField(read_only=True)
    organization_price = serializers.SerializerMethodField(read_only=True)
    profit = serializers.SerializerMethodField(read_only=True)
    profit_percentage = serializers.SerializerMethodField(read_only=True)
    employee_group = serializers.SerializerMethodField(read_only=True)
    total_ordered = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'name',
            'employee_group',
            'supplier_name',
            'sku',
            'total_cost',
            'sale_price',
            'organization_price',
            'profit',
            'profit_percentage',
            'total_ordered',
        ]

    def get_employee_group(self, obj: Product):
        return (
            EmployeeGroupCampaignProduct.objects.filter(
                product_id=obj,
                employee_group_campaign_id__campaign=self.context.get('campaign'),
            )
            .first()
            .employee_group_campaign_id.employee_group.name
        )

    def get_total_ordered(self, obj: Product):
        return obj.ordered_quantity

    def get_supplier_name(self, obj: Product):
        return obj.supplier.name

    def get_organization_price(self, obj: Product):
        return get_campaign_product_price(self.context.get('campaign'), obj)

    def get_profit(self, obj: Product):
        profit = self.get_organization_price(obj=obj) - obj.total_cost
        return profit if profit > 0 else 0

    def get_profit_percentage(self, obj: Product):
        organization_price = self.get_organization_price(obj=obj)
        if organization_price <= 0:
            return 0
        return round(
            (self.get_profit(obj=obj) / organization_price) * 100,
            2,
        )


class TextVariationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TextVariation
        fields = ('text',)


class ColorVariationSerializer(serializers.ModelSerializer):
    image = serializers.CharField(read_only=True)

    class Meta:
        model = ColorVariation
        fields = (
            'name',
            'color_code',
            'image',
        )

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        product = self.context.get('product')
        variation = self.context.get('variation')
        color_image = (
            instance.productcolorvariationimage_set.filter(product=product)
            .filter(variation=variation)
            .first()
        )
        representation['image'] = None
        if color_image and color_image.image and color_image.image.name:
            representation['image'] = color_image.image.url
        return representation


class VariationSerializer(serializers.ModelSerializer):
    text_variation = serializers.SerializerMethodField('get_text_variation')
    color_variation = serializers.SerializerMethodField('get_color_variation')

    class Meta:
        model = Variation
        fields = (
            'variation_kind',
            'system_name',
            'site_name',
            'color_variation',
            'text_variation',
        )

    def get_text_variation(self, obj):  # noqa
        return TextVariationSerializer(obj.filtered_text_variation, many=True).data

    def get_color_variation(self, obj):
        color_variations = obj.filtered_color_variation
        context = self.context.copy()
        context['product'] = self.context['product']
        context['variation'] = obj
        return ColorVariationSerializer(
            color_variations, many=True, context=context
        ).data


class ProductSerializerCampaign(DynamicFieldsSerializer):
    brand = BrandSerializer(read_only=True)
    supplier = SupplierSerializer(read_only=True)
    images = ProductImageSerializer(read_only=True, many=True)
    categories = CategorySerializer(read_only=True, many=True)
    calculated_price = serializers.SerializerMethodField(read_only=True)
    voucher_value = serializers.SerializerMethodField(read_only=True)
    extra_price = serializers.SerializerMethodField(read_only=True)
    variations = serializers.SerializerMethodField('get_variation_serializer')
    discount_rate = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'description',
            'sku',
            'link',
            'technical_details',
            'warranty',
            'exchange_value',
            'exchange_policy',
            'product_type',
            'product_kind',
            'brand',
            'supplier',
            'images',
            'categories',
            'calculated_price',
            'extra_price',
            'remaining_quantity',
            'variations',
            'voucher_type',
            'discount_rate',
            'voucher_value',
        ]

    def get_variation_serializer(self, obj):
        serializer_context = {}
        variations = Variation.objects.filter(productvariation__product=obj)
        text_variations = TextVariation.objects.filter(
            producttextvariation__product=obj
        ).distinct()

        color_variations = ColorVariation.objects.filter(
            productcolorvariationimage__product=obj
        ).distinct()

        variations = variations.prefetch_related(
            Prefetch(
                'text_variation',
                queryset=text_variations,
                to_attr='filtered_text_variation',
            ),
            Prefetch(
                'color_variation',
                queryset=color_variations,
                to_attr='filtered_color_variation',
            ),
        )

        serializer_context['product'] = obj
        serializer = VariationSerializer(
            variations, many=True, context=serializer_context
        )
        return serializer.data

    def get_voucher_value(self, obj: Product):
        employee = self.context.get('employee')
        campaign = self.context.get('campaign')
        if employee and campaign and obj.product_kind == 'MONEY':
            product: EmployeeGroupCampaignProduct = (
                EmployeeGroupCampaignProduct.objects.filter(
                    employee_group_campaign_id__campaign=self.context['campaign'],
                    employee_group_campaign_id__employee_group=self.context['employee'],
                    product_id=obj,
                ).first()
            )

            if product:
                budget = product.employee_group_campaign_id.budget_per_employee or 0
                if (
                    product.discount_mode == 'EMPLOYEE'
                    and product.organization_discount_rate
                ):
                    return round(
                        budget / (1 - (product.organization_discount_rate / 100)), 1
                    )
                else:
                    return budget
        return 0

    def get_discount_to(self, obj: Product):
        product: EmployeeGroupCampaignProduct = (
            EmployeeGroupCampaignProduct.objects.filter(
                employee_group_campaign_id__campaign=self.context['campaign'],
                employee_group_campaign_id__employee_group=self.context['employee'],
                product_id=obj,
            ).first()
        )

        return product.discount_mode if product else ''

    def get_calculated_price(self, obj: Product):
        employee = self.context.get('employee')
        campaign = self.context.get('campaign')
        return get_campaign_product_price(campaign, obj, employee)

    def get_discount_rate(self, obj: Product):
        employee = self.context.get('employee')
        campaign = self.context.get('campaign')
        if employee and campaign and obj.product_kind == 'MONEY':
            product: EmployeeGroupCampaignProduct = (
                EmployeeGroupCampaignProduct.objects.filter(
                    employee_group_campaign_id__campaign=self.context['campaign'],
                    employee_group_campaign_id__employee_group=self.context['employee'],
                    product_id=obj,
                ).first()
            )
            if product:
                return product.organization_discount_rate or 0
        return None

    def get_extra_price(self, obj):
        employee = self.context.get('employee')
        campaign = self.context.get('campaign')

        calculated_price = self.get_calculated_price(obj) or 0

        employee_group_campaign = EmployeeGroupCampaign.objects.get(
            campaign=campaign,
            employee_group=employee,
        )
        budget_per_employee = employee_group_campaign.budget_per_employee or 0
        extra_cost = calculated_price - budget_per_employee
        extra_cost = extra_cost if extra_cost > 0 else 0
        return extra_cost

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        if instance.product_kind != Product.ProductKindEnum.VARIATION.name:
            ret.pop('variations', None)

        if 'sale_price' in ret:
            del ret['sale_price']
        if 'organization_product' in ret:
            del ret['organization_product']

        return ret


class ProductSerializerQuickOffer(DynamicFieldsSerializer):
    brand = BrandSerializer(read_only=True)
    supplier = SupplierSerializer(read_only=True)
    images = ProductImageSerializer(read_only=True, many=True)
    categories = CategorySerializer(read_only=True, many=True)
    calculated_price = serializers.SerializerMethodField(read_only=True)
    variations = serializers.SerializerMethodField(read_only=True, allow_null=True)
    discount_rate = serializers.SerializerMethodField(read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'description',
            'sku',
            'link',
            'technical_details',
            'warranty',
            'exchange_value',
            'exchange_policy',
            'product_type',
            'product_kind',
            'brand',
            'supplier',
            'images',
            'categories',
            'calculated_price',
            'remaining_quantity',
            'variations',
            'discount_rate',
        ]

    def get_variations(self, obj: Product):
        serializer_context = {}
        variations = Variation.objects.filter(productvariation__product=obj)
        text_variations = TextVariation.objects.filter(
            producttextvariation__product=obj
        ).distinct()

        color_variations = ColorVariation.objects.filter(
            productcolorvariationimage__product=obj
        ).distinct()

        variations = variations.prefetch_related(
            Prefetch(
                'text_variation',
                queryset=text_variations,
                to_attr='filtered_text_variation',
            ),
            Prefetch(
                'color_variation',
                queryset=color_variations,
                to_attr='filtered_color_variation',
            ),
        )

        serializer_context['product'] = obj
        serializer = VariationSerializer(
            variations, many=True, context=serializer_context
        )
        return serializer.data

    def get_calculated_price(self, obj):
        quick_offer = self.context.get('quick_offer')
        deduct_tax = self.context.get('deduct_tax')

        calculated_price = get_quick_offer_product_price(quick_offer, obj) or 0

        if deduct_tax:
            return price_deduct_tax(calculated_price)
        else:
            return calculated_price

    def get_discount_rate(self, obj):
        quick_offer = self.context.get('quick_offer')
        quick_offer_product = QuickOfferProduct.objects.filter(
            quick_offer=quick_offer, product=obj
        ).first()
        return (
            quick_offer_product.organization_discount_rate
            if quick_offer_product and quick_offer_product.organization_discount_rate
            else 0
        )

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        if instance.product_kind != Product.ProductKindEnum.VARIATION.name:
            ret.pop('variations', None)

        if 'sale_price' in ret:
            del ret['sale_price']
        if 'organization_product' in ret:
            del ret['organization_product']

        return ret


class CartProductSerializer(serializers.ModelSerializer):
    product = ProductSerializerCampaign(read_only=True)
    variations = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CartProduct
        fields = ['id', 'product', 'quantity', 'variations']

    def get_variations(self, obj: CartProduct):
        variations: Optional[dict] = obj.variations
        if variations and self.context.get('lang') == 'he':
            variations = transform_variations(variations)
        return variations


class CartSerializer(serializers.ModelSerializer):
    products = CartProductSerializer(
        read_only=True, many=True, source='cartproduct_set'
    )

    class Meta:
        model = Cart
        fields = ['products']


class OrderProductSerializer(serializers.ModelSerializer):
    product = ProductSerializerCampaign(read_only=True)

    class Meta:
        model = OrderProduct
        fields = ['quantity', 'product']


class OrderSerializer(serializers.ModelSerializer):
    added_payment = serializers.SerializerMethodField(read_only=True)
    products = OrderProductSerializer(source='orderproduct_set', many=True)

    class Meta:
        model = Order
        fields = [
            'full_name',
            'added_payment',
            'reference',
            'order_date_time',
            'products',
            'phone_number',
            'additional_phone_number',
            'delivery_city',
            'delivery_street',
            'delivery_street_number',
            'delivery_apartment_number',
            'delivery_additional_details',
        ]

    def get_added_payment(self, obj):
        return bool(obj.cost_added and obj.cost_added > 0)


class EmployeeWithGroupSerializer(serializers.ModelSerializer):
    employee_group = EmployeeGroupSerializer()

    class Meta:
        model = Employee
        fields = '__all__'


class EmployeeLoginSerializer(serializers.Serializer):
    kwargs = {
        'required': False,
        'max_length': 255,
        'min_length': 1,
        'allow_blank': False,
        'trim_whitespace': True,
        'allow_null': False,
    }

    email = serializers.EmailField(**kwargs)
    phone_number = serializers.CharField(**kwargs)
    auth_id = serializers.CharField(**kwargs)
    otp = serializers.CharField(**kwargs)

    def validate(self, data):
        if not (data.get('email') or data.get('phone_number') or data.get('auth_id')):
            raise serializers.ValidationError(
                'Either email, phone_number or auth_id must be provided'
            )

        if data.get('phone_number'):
            # convert phone number to long form if one was provided since that
            # is how we save them in the db
            formatted_phone_number = convert_phone_number_to_long_form(
                data['phone_number']
            )

            if formatted_phone_number is None:
                raise serializers.ValidationError(
                    {'phone_number': 'Invalid phone number'}
                )
            else:
                data['phone_number'] = formatted_phone_number

        return data


class EmployeeOrderRequestSerializer(serializers.Serializer):  # sdfsd
    full_name = serializers.CharField(
        required=False, max_length=255, trim_whitespace=True
    )
    phone_number = serializers.CharField(
        required=False, max_length=255, trim_whitespace=True
    )
    additional_phone_number = serializers.CharField(
        required=False, max_length=255, trim_whitespace=True, allow_blank=True
    )
    delivery_city = serializers.CharField(
        required=False, max_length=255, trim_whitespace=True
    )
    delivery_street = serializers.CharField(
        required=False, max_length=255, trim_whitespace=True
    )
    delivery_street_number = serializers.CharField(
        required=False, max_length=255, trim_whitespace=True
    )
    delivery_apartment_number = serializers.CharField(
        required=False, max_length=255, trim_whitespace=True, allow_blank=True
    )
    delivery_additional_details = serializers.CharField(
        required=False, max_length=255, trim_whitespace=True, allow_blank=True
    )
    country = serializers.CharField(
        required=False, max_length=100, trim_whitespace=True, allow_blank=True
    )
    state_code = serializers.CharField(
        required=False, max_length=100, trim_whitespace=True, allow_blank=True
    )
    zip_code = serializers.CharField(
        required=False, max_length=100, trim_whitespace=True, allow_blank=True
    )
    size = serializers.CharField(
        required=False, max_length=100, trim_whitespace=True, allow_blank=True
    )
    color = serializers.CharField(
        required=False, max_length=100, trim_whitespace=True, allow_blank=True
    )
    variations = serializers.JSONField(required=False)

    def validate(self, data):
        errors = {}

        required_fields = [
            'phone_number',
        ]
        conditional_fields = [
            'full_name',
            'delivery_city',
            'delivery_street',
            'delivery_street_number',
        ]
        if self.context.get(
            'delivery_location'
        ) == DeliveryLocationEnum.ToOffice.name and not self.context.get(
            'one_money_product'
        ):
            required_fields = []
        if self.context.get(
            'delivery_location'
        ) == DeliveryLocationEnum.ToHome.name and not self.context.get(
            'all_money_product'
        ):
            required_fields.extend(conditional_fields)
        for k in required_fields:
            if not data.get(k):
                errors[k] = ['This field is required.']

        if (
            self.context.get('checkout_location')
            == EmployeeGroupCampaign.CheckoutLocationTypeEnum.GLOBAL.name
            and self.context.get('delivery_location')
            == DeliveryLocationEnum.ToHome.name
        ):
            for k in [
                'country',
                'state_code',
                'zip_code',
            ]:
                if not data.get(k):
                    errors[k] = ['This field is required.']
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def get_variations(self):
        variations = self.variations or {}
        if variations and self.context.get('lang') == 'he':
            variations = transform_variations(variations, mode='request')
        return variations


class OrderExportSerializer(serializers.ModelSerializer):
    campaign = CampaignSerializer(
        read_only=True, source='campaign_employee_id.campaign'
    )
    employee = EmployeeSerializer(
        read_only=True, source='campaign_employee_id.employee'
    )
    employee_group = EmployeeGroupSerializer(
        read_only=True, source='campaign_employee_id.employee.employee_group'
    )
    organization = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = '__all__'

    def get_organization(self, obj):
        return obj.campaign_employee_id.campaign.organization


class CampaignProductsGetSerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False, min_value=1, max_value=20)
    page = serializers.IntegerField(required=False, min_value=1)
    lang = serializers.ChoiceField(
        choices=settings.MODELTRANSLATION_LANGUAGES,
        required=False,
        error_messages={
            'invalid_choice': (
                'Provided choice is invalid. '
                f'Available choices are: {settings.MODELTRANSLATION_LANGUAGES}'
            )
        },
    )
    category_id = serializers.IntegerField(required=False)
    q = serializers.CharField(max_length=255, required=False)
    original_budget = serializers.ChoiceField(choices=(1, 0), required=False)
    budget = serializers.ChoiceField(choices=(1, 2, 3), required=False)
    sort = serializers.ChoiceField(choices=('asc', 'desc'), required=False)
    sub_categories = serializers.CharField(max_length=510, required=False)
    brands = serializers.CharField(max_length=510, required=False)
    min_price = serializers.IntegerField(required=False)
    max_price = serializers.IntegerField(required=False)
    product_type = serializers.CharField(max_length=128, required=False)


class CartAddProductSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=0)
    variations = serializers.JSONField(required=False, allow_null=True)

    def validate(self, data):
        product_id = data.get('product_id')
        product = Product.objects.filter(id=product_id).first()
        if product and product.remaining_quantity < data.get('quantity'):
            raise serializers.ValidationError(
                {
                    'quantity': gettext(
                        (
                            'The requested quantity is not available. '
                            'The remaining quantity is %(remaining_quantity)d.'
                        )
                    )
                    % {'remaining_quantity': product.remaining_quantity}
                }
            )
        return data

    def validate_variations(self, value):
        if value and len(value) > 5:
            raise serializers.ValidationError('Variations cannot exceed 5 items.')
        return value


class CampaignExchangeRequestSerializer(serializers.Serializer):
    t = serializers.CharField(required=True)


class ShareRequestSerializer(serializers.Serializer):
    share_type = serializers.CharField(max_length=100, required=True)
    product_ids = serializers.ListField(child=serializers.IntegerField(), required=True)


class FilterLookupSerializer(serializers.Serializer):
    lookup_choices = ['product_kinds', 'brands', 'sub_categories', 'max_price']
    lookup = serializers.ChoiceField(
        choices=lookup_choices,
        error_messages={
            'invalid_choice': (
                'Provided choice is invalid. '
                f'Available choices are: {",".join(lookup_choices)}'
            )
        },
    )
    budget = serializers.IntegerField(required=False)
    including_tax = serializers.BooleanField(required=False, default=True)
    q = serializers.CharField(max_length=255, required=False)
    category = serializers.CharField(max_length=255, required=False)
    sub_categories = serializers.CharField(max_length=512, required=False)
    product_kinds = serializers.CharField(max_length=512, required=False)
    brands = serializers.CharField(max_length=512, required=False)

    def validate(self, data):
        """
        Check the subcategories, product_kinds and brands values.
        """
        if data.get('sub_categories') and not all(
            item.isnumeric() for item in data['sub_categories'].split(',')
        ):
            raise serializers.ValidationError(
                {'sub_categories': 'invalid value ,The expected value is 1,2,3,....'}
            )
        if data.get('brands') and not all(
            item.isnumeric() for item in data['brands'].split(',')
        ):
            raise serializers.ValidationError(
                {'brands': 'invalid value ,The expected value is 1,2,3,....'}
            )
        if data.get('product_kinds') and not all(
            item in [product_kind.name for product_kind in Product.ProductKindEnum]
            for item in data['product_kinds'].split(',')
        ):
            enum_values = [
                product_kind.name for product_kind in Product.ProductKindEnum
            ]
            raise serializers.ValidationError(
                {'product_kinds': f'invalid value ,kinds names:{enum_values}'}
            )
        return data


class FilterLookupBrandsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = (
            'id',
            'name',
        )


class FilterLookupProductKindsSerializer(serializers.Serializer):
    id = serializers.CharField()  # Corresponds to the enum name
    name = serializers.CharField()


class FilterLookupTagsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = (
            'id',
            'name',
        )


class ProductSerializerQuickOfferAdmin(DynamicFieldsSerializer):
    supplier_name = serializers.SerializerMethodField(read_only=True)
    organization_price = serializers.SerializerMethodField(read_only=True)
    profit = serializers.SerializerMethodField(read_only=True)
    profit_percentage = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'name',
            'supplier_name',
            'sku',
            'total_cost',
            'sale_price',
            'organization_price',
            'profit',
            'profit_percentage',
        ]

    def get_supplier_name(self, obj: Product):
        return obj.supplier.name

    def get_organization_price(self, obj: Product):
        return get_quick_offer_product_price(self.context.get('quick_offer'), obj)

    def get_profit(self, obj: Product):
        profit = self.get_organization_price(obj=obj) - obj.total_cost
        return profit if profit else 0

    def get_profit_percentage(self, obj: Product):
        try:
            return round(
                (self.get_profit(obj=obj) / self.get_organization_price(obj=obj)) * 100,
                2,
            )
        except Exception:
            return None


class QuickOfferTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuickOfferTag
        fields = ('name',)


class QuickOfferUpdateSendMyOrderSerializer(serializers.Serializer):
    send_my_list = serializers.BooleanField(required=True)


class QuickOfferSerializer(serializers.ModelSerializer):
    organization_name = serializers.SerializerMethodField(
        read_only=True, allow_null=True
    )
    organization_logo_image = serializers.SerializerMethodField(
        read_only=True, allow_null=True
    )

    class Meta:
        model = QuickOffer
        fields = [
            'organization_name',
            'organization_logo_image',
            'name',
            'code',
            'quick_offer_type',
            'ship_to',
            'status',
            'login_page_title',
            'login_page_subtitle',
            'main_page_first_banner_title',
            'main_page_first_banner_subtitle',
            'main_page_first_banner_image',
            'main_page_first_banner_mobile_image',
            'main_page_second_banner_title',
            'main_page_second_banner_subtitle',
            'main_page_second_banner_background_color',
            'main_page_second_banner_text_color',
            'sms_sender_name',
            'sms_welcome_text',
            'email_welcome_text',
            'login_page_image',
            'login_page_mobile_image',
            'auth_method',
            'phone_number',
            'email',
            'nicklas_status',
            'client_status',
            'last_login',
            'selected_products',
            'send_my_list',
        ]

    def get_organization_name(self, obj: QuickOffer):
        return obj.organization.name

    def get_organization_logo_image(self, obj: QuickOffer):
        return obj.organization.logo_image.url if obj.organization.logo_image else ''


class QuickOfferReadOnlySerializer(serializers.ModelSerializer):
    organization_name = serializers.SerializerMethodField(
        read_only=True, allow_null=True
    )
    organization_logo_image = serializers.SerializerMethodField(
        read_only=True, allow_null=True
    )

    class Meta:
        model = QuickOffer
        fields = [
            'name',
            'code',
            'is_active',
            'organization_name',
            'organization_logo_image',
            'login_page_title',
            'login_page_subtitle',
            'login_page_image',
            'login_page_mobile_image',
        ]

    def get_organization_name(self, obj: QuickOffer):
        return obj.organization.name

    def get_organization_logo_image(self, obj: QuickOffer):
        return obj.organization.logo_image.url if obj.organization.logo_image else ''


class OrganizationLoginSerializer(serializers.Serializer):
    otp = serializers.CharField(required=False, max_length=255)
    auth_id = serializers.CharField(required=False, max_length=255)


class QuickOfferProductsRequestSerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False, min_value=1, max_value=20)
    page = serializers.IntegerField(required=False, min_value=1)
    lang = serializers.ChoiceField(
        choices=settings.MODELTRANSLATION_LANGUAGES,
        required=False,
        error_messages={
            'invalid_choice': (
                'Provided choice is invalid. '
                f'Available choices are: {settings.MODELTRANSLATION_LANGUAGES}'
            )
        },
    )
    category_id = serializers.IntegerField(required=False)
    q = serializers.CharField(max_length=255, required=False)
    including_tax = serializers.BooleanField(default=True, required=False)
    sort = serializers.ChoiceField(choices=('asc', 'desc'), required=False)
    sub_categories = serializers.CharField(max_length=510, required=False)
    brands = serializers.CharField(max_length=510, required=False)
    min_price = serializers.FloatField(
        required=False,
        min_value=0.0,  # Optional: ensures non-negative values
    )
    max_price = serializers.FloatField(
        required=False,
        min_value=0.0,  # Optional: ensures non-negative values
    )
    product_type = serializers.CharField(max_length=128, required=False)


class QuickOfferProductRequestSerializer(serializers.Serializer):
    lang = serializers.ChoiceField(
        choices=settings.MODELTRANSLATION_LANGUAGES,
        required=False,
        error_messages={
            'invalid_choice': (
                'Provided choice is invalid. '
                f'Available choices are: {settings.MODELTRANSLATION_LANGUAGES}'
            )
        },
    )
    including_tax = serializers.BooleanField(default=True, required=False)


class QuickOfferProductsResponseSerializer(DynamicFieldsSerializer):
    brand = BrandSerializer(read_only=True)
    supplier = SupplierSerializer(read_only=True)
    images = ProductImageSerializer(read_only=True, many=True)
    categories = CategorySerializer(read_only=True, many=True)
    calculated_price = serializers.SerializerMethodField(read_only=True)
    special_offer = serializers.SerializerMethodField(read_only=True, allow_null=True)
    variations = serializers.SerializerMethodField(read_only=True, allow_null=True)
    voucher_value = serializers.SerializerMethodField(read_only=True, allow_null=True)
    discount_rate = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'description',
            'sku',
            'link',
            'technical_details',
            'warranty',
            'exchange_value',
            'exchange_policy',
            'product_type',
            'product_kind',
            'brand',
            'supplier',
            'images',
            'categories',
            'calculated_price',
            'remaining_quantity',
            'special_offer',
            'variations',
            'voucher_value',
            'discount_rate',
        ]

    def get_variations(self, obj: Product):
        serializer_context = {}
        variations = Variation.objects.filter(productvariation__product=obj)
        text_variations = TextVariation.objects.filter(
            producttextvariation__product=obj
        ).distinct()

        color_variations = ColorVariation.objects.filter(
            productcolorvariationimage__product=obj
        ).distinct()

        variations = variations.prefetch_related(
            Prefetch(
                'text_variation',
                queryset=text_variations,
                to_attr='filtered_text_variation',
            ),
            Prefetch(
                'color_variation',
                queryset=color_variations,
                to_attr='filtered_color_variation',
            ),
        )

        serializer_context['product'] = obj
        serializer = VariationSerializer(
            variations, many=True, context=serializer_context
        )
        return serializer.data

    def get_special_offer(self, obj: Product):
        if obj.offer:
            special_offers = SPECIAL_OFFER_ENUM_TRANSLATIONS
            return special_offers.get(self.context.get('lang', 'en')).get(obj.offer)
        return ''

    def get_voucher_value(self, obj: Product):
        prd = QuickOfferProduct.objects.filter(product=obj).first()
        if prd:
            return prd.organization_discount_rate
        return 0

    def get_discount_rate(self, obj):
        quick_offer = self.context.get('quick_offer')
        quick_offer_product = QuickOfferProduct.objects.filter(
            quick_offer=quick_offer, product=obj
        ).first()
        return (
            quick_offer_product.organization_discount_rate
            if quick_offer_product and quick_offer_product.organization_discount_rate
            else 0
        )

    def get_calculated_price(self, obj):
        quick_offer = self.context.get('quick_offer')
        deduct_tax = self.context.get('deduct_tax')

        calculated_price = get_quick_offer_product_price(quick_offer, obj) or 0

        if deduct_tax:
            return price_deduct_tax(calculated_price)
        else:
            return calculated_price

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        if 'sale_price' in ret:
            del ret['sale_price']
        if 'organization_product' in ret:
            del ret['organization_product']

        return ret


class QuickOfferProductSerializer(QuickOfferProductsResponseSerializer):
    calculated_price = serializers.SerializerMethodField(read_only=True)

    def get_calculated_price(self, obj):
        quick_offer = self.context.get('quick_offer')
        deduct_tax = self.context.get('deduct_tax')

        calculated_price = get_quick_offer_product_price(quick_offer, obj) or 0

        if deduct_tax:
            return price_deduct_tax(calculated_price)
        else:
            return calculated_price


class QuickOfferSelectProductsSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=0)
    variations = serializers.JSONField(required=False, allow_null=True)

    def validate_variations(self, value):
        if value and len(value) > 5:
            raise serializers.ValidationError('Variations cannot exceed 5 items.')
        return value


class QuickOfferSelectProductsDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    product = ProductSerializerQuickOffer(read_only=True)
    quantity = serializers.IntegerField(min_value=0)
    variations = serializers.JSONField(read_only=True, allow_null=True)

    class Meta:
        model = QuickOfferSelectedProduct
        fields = ['id', 'product', 'quantity', 'variations']

    def get_variations(self):
        variations = self.variations or {}
        if variations and self.context.get('lang') == 'he':
            variations = transform_variations(variations)
        return variations


class AvailableQuickOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuickOffer
        fields = ['id', 'name']


class OrganizationProductPutSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationProduct
        fields = '__all__'
