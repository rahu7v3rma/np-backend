import os
from typing import Any
import uuid

from dal import autocomplete
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.http import HttpResponse
from django.urls import reverse
from django.utils.datastructures import MultiValueDict
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from modeltranslation.admin import TranslationAdmin
from openpyxl import Workbook

from campaign.models import Campaign, EmployeeGroupCampaignProduct
from common.mixins import ActiveObjectsAdminMixin
from inventory.models import (
    Brand,
    BrandSupplier,
    Category,
    CategoryProduct,
    Product,
    ProductBundleItem,
    ProductImage,
    Supplier,
    Tag,
)
from lib.admin import ImportableExportableAdmin, RecordImportError
from logistics.tasks import sync_product_with_logistics_center
from services.email import send_stock_alert_email

from .admin_forms import ModelWithImagesXlsxImportForm


class ProductImageInlineFormset(forms.models.BaseInlineFormSet):
    def clean(self):
        main_exists = False
        check = False
        count = 0
        if len(self.forms) == 0:
            return
        for form in self.forms:
            if form.cleaned_data:
                count += 1
                if not form.cleaned_data.get('DELETE'):
                    check = True
                if form.cleaned_data.get('main') and form.cleaned_data.get('DELETE'):
                    continue
            main_exists = form.cleaned_data.get('main', False) or main_exists

        if count == 1:
            self.forms[0].cleaned_data['main'] = True
            return
        if not main_exists and check:
            raise forms.ValidationError('The main image should be selected')


class ProductImagesInline(admin.TabularInline):
    model = ProductImage
    formset = ProductImageInlineFormset


@admin.register(Brand)
class BrandAdmin(ActiveObjectsAdminMixin, ImportableExportableAdmin):
    list_display = ('name', 'logo', 'is_deleted', 'updated_at')
    change_list_template = 'admin/import_changelist.html'

    list_filter = ('is_deleted',)
    fieldsets = [
        (
            None,
            {
                'fields': (
                    'is_deleted',
                    'name',
                    'logo_image',
                    'updated_at',
                    'created_at',
                ),
            },
        ),
        ('BRAND PRODUCTS', {'fields': ('brand_products_link',)}),
    ]
    readonly_fields = (
        'updated_at',
        'created_at',
        'brand_products_link',
    )
    search_fields = ('name',)

    import_form = ModelWithImagesXlsxImportForm

    def get_inlines(self, request, obj):
        return [BrandSupplierInline] if obj else []

    def import_parse_field(
        self,
        name: str,
        value: str,
        extra_params: dict[str, Any],
        extra_files: MultiValueDict,
    ):
        if name == 'logo_image' and value:
            image_files = [
                i for i in extra_files.getlist('image_dir') if i.name == value
            ]

            if image_files:
                return image_files[0]
            else:
                raise ValueError(f'Image file {value} not found in uploaded directory')

        return super().import_parse_field(name, value, extra_params, extra_files)

    def logo(self, obj):
        if obj.logo_image:
            return format_html(
                '<img src="{}" style="max-width:100px; max-height:100px"/>'.format(
                    obj.logo_image.url
                )
            )
        return None

    def brand_products_link(self, obj):
        count = obj.brand_products.count()

        brand_product_changelist_url = reverse('admin:inventory_product_changelist')
        search_params = urlencode({'brand__id__exact': obj.id})

        return mark_safe(
            f'<a href="{brand_product_changelist_url}?{search_params}">'
            f'Total products: {count}</a>'
        )

    brand_products_link.short_description = 'Brand products'


class BrandSupplierInline(admin.TabularInline):
    model = BrandSupplier
    extra = 1


@admin.register(Supplier)
class SupplierAdmin(ActiveObjectsAdminMixin, ImportableExportableAdmin):
    list_display = (
        'name',
        'email',
        'phone_number',
        'is_deleted',
        'updated_at',
    )
    list_filter = ('is_deleted',)
    fieldsets = [
        (
            None,
            {
                'fields': (
                    'is_deleted',
                    'name',
                    'house_number',
                    'address_city',
                    'address_street',
                    'address_street_number',
                    'email',
                    'phone_number',
                    'updated_at',
                    'created_at',
                ),
            },
        ),
        ('SUPPLIER PRODUCTS', {'fields': ('supplier_products_link',)}),
    ]
    readonly_fields = (
        'updated_at',
        'created_at',
        'supplier_products_link',
    )
    change_list_template = 'admin/import_changelist.html'
    search_fields = [
        'name_en',
        'name_he',
        'address_city_en',
        'address_city_he',
        'address_street_en',
        'address_street_he',
        'address_street_number_en',
        'address_street_number_he',
        'email',
        'phone_number',
        'house_number',
    ]

    def get_inlines(self, request, obj):
        return [BrandSupplierInline] if obj else []

    def supplier_products_link(self, obj):
        count = obj.supplier_products.count()

        supplier_product_changelist_url = reverse('admin:inventory_product_changelist')
        search_params = urlencode({'supplier__id__exact': obj.id})

        return mark_safe(
            f'<a href="{supplier_product_changelist_url}?{search_params}">'
            f'Total products: {count}</a>'
        )

    supplier_products_link.short_description = 'Supplier products'


def custom_titled_filter(title):
    class Wrapper(admin.FieldListFilter):
        def __new__(cls, *args, **kwargs):
            instance = admin.FieldListFilter.create(*args, **kwargs)
            instance.title = title
            return instance

    return Wrapper


class PriceFilter(admin.SimpleListFilter):
    title = 'Product Price Filter'
    parameter_name = 'cost_price'

    def lookups(self, request, model_admin):
        return (
            ('0-19', '0-19'),
            ('20-39', '20-39'),
            ('40-59', '40-59'),
            ('60<=', '60<='),
        )

    def queryset(self, request, queryset):
        if self.value() == '0-19':
            return queryset.filter(cost_price__lte=19)
        if self.value() == '20-39':
            return queryset.filter(cost_price__range=(20, 39))
        if self.value() == '40-59':
            return queryset.filter(cost_price__range=(40, 59))
        if self.value() == '60<=':
            return queryset.filter(cost_price__gte=60)


class CategoryInline(admin.TabularInline):
    model = Category.product_set.through
    extra = 1


class TagInline(admin.TabularInline):
    model = Tag.product_set.through
    extra = 1


class BundledProductInlineForm(forms.ModelForm):
    class Meta:
        model = ProductBundleItem
        fields = '__all__'
        widgets = {
            'product': autocomplete.ModelSelect2(url='bundled-product-autocomplete')
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # override label from instance to set the inital selected label before
        # the select widget was used
        self.fields['product'].label_from_instance = (
            lambda obj: f'{obj.sku} - {obj.name}'
        )


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'

    def full_clean(self):
        # disable the required flag for fields that are calculated
        # automatically for bundle products. after the first clean we can check
        # if the object is a bundle and if not restore the flags and re-clean
        self.fields['sku'].required = False
        self.fields['supplier'].required = False
        self.fields['brand'].required = False
        self.fields['cost_price'].required = False

        super().full_clean()

        self.fields['sku'].required = True
        self.fields['supplier'].required = True
        self.fields['brand'].required = True
        self.fields['cost_price'].required = True

        if self.cleaned_data['product_kind'] != Product.ProductKindEnum.BUNDLE.name:
            # clean again with the required flags back
            super().full_clean()

    def clean(self):
        cleaned_data = super().clean()

        # for new bundle items set initial placeholder values for the required
        # fields, and they will be populated later when the bundled items form
        # is saved
        if cleaned_data['product_kind'] == Product.ProductKindEnum.BUNDLE.name:
            if not cleaned_data['sku']:
                cleaned_data['sku'] = 'PLACEHOLDER'
            if not cleaned_data['cost_price']:
                cleaned_data['cost_price'] = -1
            if not cleaned_data['brand']:
                cleaned_data['brand'] = Brand.objects.first()
            if not cleaned_data['supplier']:
                cleaned_data['supplier'] = Supplier.objects.first()

        return cleaned_data


class BundledProductsInline(admin.TabularInline):
    model = ProductBundleItem
    extra = 1
    fk_name = 'bundle'
    form = BundledProductInlineForm


@admin.register(Product)
class ProductAdmin(ImportableExportableAdmin):
    search_fields = ['name', 'brand__name', 'supplier__name']
    change_list_template = 'admin/import_changelist.html'
    change_form_template = 'admin/product_change_form.html'
    actions = ['duplicate', 'export_as_xlsx', 'sync_with_logistic_center']
    inlines = [CategoryInline, TagInline, ProductImagesInline, BundledProductsInline]
    form = ProductAdminForm
    readonly_fields = ['total_cost']

    list_display = (
        'name',
        'brand',
        'supplier',
        'active',
        'product_type',
        'product_quantity',
        'remaining_quantity',
        'cost_price',
        'sku',
        'main_image',
        'active_campaigns',
    )
    list_filter = (
        'categories',
        'tags',
        ('brand__name', custom_titled_filter('brand')),
        ('supplier__name', custom_titled_filter('supplier')),
        PriceFilter,
        'active',
        'product_quantity',
    )

    import_form = ModelWithImagesXlsxImportForm
    import_related_fields = ('categories', 'tags', 'images')
    import_excluded_fields = ('active_campaigns',)
    fields = (
        'name_en',
        'name_he',
        'sku',
        'reference',
        'product_kind',
        'product_type',
        'product_quantity',
        'supplier',
        'brand',
        'offer',
        'link',
        'active',
        'cost_price',
        'delivery_price',
        'logistics_rate_cost_percent',
        'total_cost',
        'google_price',
        'sale_price',
        'exchange_value',
        'description_en',
        'description_he',
        'technical_details_en',
        'technical_details_he',
        'warranty_en',
        'warranty_he',
        'exchange_policy_en',
        'exchange_policy_he',
    )

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)

        # if the current formset we are saving is the bundled products formset
        # (as toled by the type of its empty form) make sure to update the
        # parent product's calculated fields
        if isinstance(formset.empty_form, BundledProductInlineForm):
            form.instance.update_bundle_calculated_fields()

    def export_as_xlsx(self, request, queryset):
        field_names = [
            'id',
            'brand',
            'supplier',
            'reference',
            'name_en',
            'name_he',
            'product_kind',
            'product_type',
            'description_en',
            'description_he',
            'sku',
            'link',
            'active',
            'cost_price',
            'delivery_price',
            'logistics_rate_cost_percent',
            'total_cost',
            'google_price',
            'sale_price',
            'technical_details_en',
            'technical_details_he',
            'warranty_en',
            'warranty_he',
            'exchange_value',
            'exchange_policy_en',
            'exchange_policy_he',
            'categories',
            'tags',
            'active_campaigns',
            'product_quantity',
        ]

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=inventory.products.xlsx'

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(field_names)

        for _product in queryset:
            category = _product.categories.all().first()
            category = category.name if category else ''
            tags = _product.tags.all().first()
            tags = tags.name if tags else ''
            worksheet.append(
                [
                    _product.id,
                    _product.brand.name,
                    _product.supplier.name,
                    _product.reference,
                    _product.name_en,
                    _product.name_he,
                    _product.product_kind,
                    _product.product_type,
                    _product.description_en,
                    _product.description_he,
                    _product.sku,
                    _product.link,
                    _product.active,
                    _product.cost_price,
                    _product.delivery_price,
                    _product.logistics_rate_cost_percent,
                    _product.total_cost,
                    _product.google_price,
                    _product.sale_price,
                    _product.technical_details_en,
                    _product.technical_details_he,
                    _product.warranty_en,
                    _product.warranty_he,
                    _product.exchange_value,
                    _product.exchange_policy_en,
                    _product.exchange_policy_he,
                    category,
                    tags,
                    self.active_campaigns(obj=_product),
                    _product.product_quantity,
                ]
            )

        workbook.save(response)
        return response

    export_as_xlsx.short_description = 'Export selected products as XLSX'

    def import_parse_and_save_xlsx_data(
        self, extra_params: dict[str, Any], request_files: MultiValueDict
    ):
        if len(request_files) == 0:
            raise Exception(
                _(
                    'Either an XLSX file or a directory containing images '
                    'must be selected.'
                )
            )
        elif 'xlsx_file' in request_files:
            return super().import_parse_and_save_xlsx_data(extra_params, request_files)
        else:
            # if only other files were sent this is an image-only import
            return self._import_and_save_image_date(request_files)

    def import_parse_field(
        self,
        name: str,
        value: str,
        extra_params: dict[str, Any],
        extra_files: MultiValueDict,
    ):
        if name == 'brand':
            return Brand.objects.get(name__iexact=value)
        elif name == 'supplier':
            return Supplier.objects.get(name__iexact=value)
        elif name == 'product_quantity' and (not value or int(value) < 0):
            raise ValidationError(
                {'product_quantity': [_('Product quantity must be a positive number')]}
            )

        return super().import_parse_field(name, value, extra_params, extra_files)

    def import_parse_related_field(
        self,
        name: str,
        value: str,
        extra_files: MultiValueDict,
        main_record: models.Model,
    ):
        if name == 'categories':
            parsed_values = []
            for v in self._import_split_field_value(value):
                if v:
                    parsed_values.append(Category.objects.get(name__iexact=v))

            if len(parsed_values) == 0:
                raise ValidationError(
                    {'categories': ['Must provide at least one category']}
                )

            return parsed_values
        elif name == 'tags':
            parsed_values = []
            for v in self._import_split_field_value(value):
                if v:
                    parsed_values.append(Tag.objects.get(name__iexact=v))

            if len(parsed_values) == 0:
                raise ValidationError({'tags': ['Must provide at least one tag']})

            return parsed_values
        elif name == 'images':
            parsed_values = []

            for v in self._import_split_field_value(value):
                if v:
                    image_files = [
                        i for i in extra_files.getlist('image_dir') if i.name == v
                    ]

                    if image_files:
                        is_main = len(parsed_values) == 0

                        new_image = ProductImage.objects.create(
                            product=main_record, main=is_main
                        )
                        new_image.image.save(
                            image_files[0].name, ContentFile(image_files[0].read())
                        )

                        parsed_values.append(new_image)
                    else:
                        raise ValueError(
                            f'Image file {v} not found in uploaded directory'
                        )

            return parsed_values

        raise ValueError(f'Failed to parse related field: {name}')

    def _import_and_save_image_date(self, request_files: MultiValueDict):
        updated_images = 0
        errors = {}

        processed_product_ids = []

        for f in request_files.getlist('image_dir'):
            try:
                if not f.content_type.startswith('image'):
                    raise Exception('File is not an image')

                sku, _ = os.path.splitext(f.name)

                split_sku = sku.rsplit('_', 1)
                sku = split_sku[0]
                image_index = split_sku[1] if len(split_sku) > 1 else None

                product = Product.objects.filter(sku=sku).first()

                if not product:
                    raise Exception('Product with provided sku was not found')

                # delete existing product images if this is the first time we
                # process this product
                if product.id not in processed_product_ids:
                    ProductImage.objects.filter(product=product).delete()
                    processed_product_ids.append(product.id)

                # the image will be set as main if its image index is none (aka
                # its file name is '{sku}.png' with no image index), or if no
                # other image is currently set as main. this should prevent an
                # issue where all imported images have indices an so none will
                # be set as main
                is_main = (
                    image_index is None
                    or ProductImage.objects.filter(product=product, main=True).first()
                    is None
                )

                new_image = ProductImage.objects.create(product=product, main=is_main)
                new_image.image.save(f.name, ContentFile(f.read()))

                updated_images += 1
            except Exception as ex:
                msg = str(ex)

                if msg not in errors:
                    errors[msg] = []

                errors[msg].append(f.name)

        if errors:
            raise RecordImportError(errors)
        else:
            return 0, updated_images

    def duplicate(self, request, queryset):
        for obj in queryset:
            product_id = obj.id
            obj.id = None
            obj.name = f'duplicate_{obj.name}'
            obj.sku = f'duplicate__{uuid.uuid4()}'
            obj.save()
            for image in ProductImage.objects.filter(product__id=product_id).all():
                image.id = None
                image.product = obj
                image.save()

    def sync_with_logistic_center(self, request, queryset):
        for obj in queryset:
            sync_product_with_logistics_center.apply_async((obj.pk,))

        self.message_user(
            request,
            f'Will sync {len(queryset)} products with logistics center...',
            level=messages.SUCCESS,
        )

    def main_image(self, obj):
        if obj.main_image:
            return format_html(
                '<img src="{}" style="max-width:100px; max-height:100px"/>'.format(
                    obj.main_image
                )
            )
        return None

    def save_model(self, request, obj, form, change):
        obj.clean()
        super().save_model(request, obj, form, change)

    def active_campaigns(self, obj):
        campaign_ids = EmployeeGroupCampaignProduct.objects.filter(
            product_id=obj
        ).values_list('employee_group_campaign_id__campaign', flat=True)
        campaigns = Campaign.objects.filter(
            id__in=campaign_ids, status=Campaign.CampaignStatusEnum.ACTIVE.name
        ).values_list('name', flat=True)
        active_campaign_str = ', '.join(campaigns)
        return active_campaign_str

    def changelist_view(self, request, extra_context=None):
        products = Product.objects.annotate(
            remaining_quantity_db=models.F('product_quantity')
            - models.Sum('employeegroupcampaignproduct__orderproduct__quantity')
        ).filter(remaining_quantity_db__lte=settings.STOCK_LIMIT_THRESHOLD)
        if len(products):
            self.message_user(
                request,
                (
                    'The following products reached the'
                    ' stock threshold :'
                    f' {",".join(list(products.values_list("name", flat=True)))}'
                ),
                messages.WARNING,
            )

        alert_products = products.filter(alert_stock_sent=False).all()
        if len(alert_products) > 0:
            send_email_response = send_stock_alert_email(
                settings.DEFAULT_FROM_EMAIL,
                ','.join(list(products.values_list('name', flat=True))),
            )
            if send_email_response:
                alert_products.update(alert_stock_sent=True)
        return super().changelist_view(request, extra_context)


class CategoryProductInline(admin.TabularInline):
    model = CategoryProduct
    extra = 0
    fields = ['product_id']
    readonly_fields = ['product_id']
    show_change_link = True
    can_delete = False
    template = 'inventory/category_product_inline.html'

    def has_add_permission(self, request, obj):
        return False


@admin.register(Category)
class CategoryAdmin(TranslationAdmin):
    list_display = ('name',)

    def get_inlines(self, request, obj):
        return [CategoryProductInline] if obj else []


@admin.register(Tag)
class TagAdmin(TranslationAdmin):
    list_display = ('name',)
