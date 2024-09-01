import json
import os
from typing import Any
import uuid

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.utils.datastructures import MultiValueDict
from django.utils.html import format_html
from django.utils.translation import gettext as _
from modeltranslation.admin import TranslationAdmin
from openpyxl import load_workbook

from campaign.models import Campaign, EmployeeGroupCampaignProduct
from inventory.models import Brand, Category, Product, ProductImage, Supplier, Tag
from lib.admin import ImportableExportableAdmin, RecordImportError
from logistics.tasks import sync_product_with_logistics_center

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


class ProductsInline(admin.TabularInline):
    model = Product
    fields = ['name']
    readonly_fields = ['name']
    show_change_link = True
    can_delete = False
    template = 'inventory/product_inline.html'

    def has_add_permission(self, request, obj):
        return False


@admin.register(Brand)
class BrandAdmin(ImportableExportableAdmin):
    list_display = ('name', 'logo')
    change_list_template = 'admin/import_changelist.html'

    import_form = ModelWithImagesXlsxImportForm

    def get_inlines(self, request, obj):
        return [ProductsInline] if obj else []

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


@admin.register(Supplier)
class SupplierAdmin(ImportableExportableAdmin):
    list_display = ('name',)
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
    ]

    def get_inlines(self, request, obj):
        return [ProductsInline] if obj else []


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


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sku'].widget = forms.TextInput()
        # Store the choices in an attribute
        self.sku_choices = self.get_sku_choices()
        self.products = self.get_product_data()
        if self.instance and self.instance.pk:
            self.selected_skus = (
                self.instance.sku.split(',') if self.instance.sku else []
            )

    def get_sku_choices(self):
        skus = Product.objects.exclude(
            product_kind=Product.ProductKindEnum.BUNDLE.name
        ).values_list('sku', flat=True)
        return [sku for sku in skus]

    def get_product_data(self):
        products = Product.objects.exclude(
            product_kind=Product.ProductKindEnum.BUNDLE.name
        ).values(
            'sku',
            'cost_price',
            'delivery_price',
            'logistics_rate_cost_percent',
            'google_price',
            'sale_price',
            'brand',
        )
        data = list(products)
        return data

    def clean_skus(self):
        skus = self.cleaned_data.get('sku')
        if skus:
            return [sku.strip() for sku in skus.split(',') if sku.strip()]
        return []


@admin.register(Product)
class ProductAdmin(ImportableExportableAdmin):
    search_fields = ['name', 'brand__name', 'supplier__name']
    change_list_template = 'admin/import_changelist.html'
    change_form_template = 'admin/product_change_form.html'
    actions = ['duplicate', 'export_as_xlsx', 'sync_with_logistic_center']
    inlines = [CategoryInline, TagInline, ProductImagesInline]
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
    export_fields = (
        'id',
        'brand__name',
        'supplier__name',
        'reference',
        'name_en',
        'name_he',
        'product_kind',
        'product_type',
        'product_quantity',
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
        'categories__name_en',
        'tags__name_en',
    )

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
            # if an xlsx file was sent this is a normal import and the shared
            # logic can be called
            wb = load_workbook(
                request_files.get('xlsx_file'), data_only=True, read_only=True
            )
            columns = [c.value for c in next(wb.active.iter_rows(min_row=1, max_row=1))]

            if 'product_quantity' not in columns:
                raise Exception(_('product_quantity column is required'))

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

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        form_class = self.get_form(request)
        instance = self.get_object(request, object_id) if object_id else None

        form = form_class(instance=instance)

        sku_choices = getattr(form, 'sku_choices', [])
        products = getattr(form, 'products', [])
        try:
            sku_choices_json = json.dumps(sku_choices)
            products_json = json.dumps(products)
        except (TypeError, OverflowError):
            sku_choices_json = '[]'
            products_json = '[]'

        extra_context = extra_context or {}
        extra_context['sku_choices'] = sku_choices_json
        extra_context['products'] = products_json
        extra_context['supplier_brands'] = json.dumps(
            list(Supplier.objects.all().values('id', 'brands__id', 'brands__name')))

        return super().changeform_view(
            request, object_id, form_url, extra_context=extra_context
        )

    def active_campaigns(self, obj):
        campaign_ids = EmployeeGroupCampaignProduct.objects.filter(
            product_id=obj
        ).values_list('employee_group_campaign_id__campaign', flat=True)
        campaigns = Campaign.objects.filter(
            id__in=campaign_ids, status=Campaign.CampaignStatusEnum.ACTIVE.name
        ).values_list('name', flat=True)
        active_campaign_str = ', '.join(campaigns)
        return active_campaign_str


@admin.register(Category)
class CategoryAdmin(TranslationAdmin):
    list_display = ('name',)


@admin.register(Tag)
class TagAdmin(TranslationAdmin):
    list_display = ('name',)
