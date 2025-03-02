import io
from urllib.parse import urlencode
import zipfile

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import ValidationError
from django.db.models import (
    Case,
    F,
    Func,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _, ngettext
from openpyxl import Workbook
from rest_framework.reverse import reverse as drf_reverse

from campaign.models import Order
from campaign.tasks import snake_to_title
from inventory.models import Brand, Product, Supplier, Variation

from .forms import SearchForm
from .models import (
    EmployeeOrderProduct,
    LogisticsCenterInboundReceiptLine,
    POOrder,
    PurchaseOrder,
    PurchaseOrderProduct,
)
from .tasks import (
    export_order_summaries_as_xlsx_task,
    send_purchaseorder_to_supplier,
)
from .utils import (
    exclude_taxes,
    get_variation_type,
    get_variations_string,
    update_order_products_po_status,
)


class Round(Func):
    function = 'ROUND'
    template = '%(function)s(%(expressions)s, 2)'


def custom_titled_filter(title):
    class Wrapper(admin.FieldListFilter):
        def __new__(cls, *args, **kwargs):
            instance = admin.FieldListFilter.create(*args, **kwargs)
            instance.title = title
            return instance

    return Wrapper


class POFilter(admin.SimpleListFilter):
    title = 'PO Number'
    parameter_name = 'id'
    chunk_size = 10
    _range = []

    def lookups(self, request, model_admin):
        data_list = POOrder.objects.order_by('id').values_list('id')
        self._range = [
            f'{str(data_list[i : i + self.chunk_size][0][0])}-{str(data_list[i : i + self.chunk_size][-1][0])}'  # noqa: E501
            for i in range(0, len(data_list), self.chunk_size)
        ]
        return [(el, el) for el in self._range]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        min = self.value().split('-')[0]
        max = self.value().split('-')[1]
        return queryset.filter(id__lte=int(max), id__gte=int(min))


@admin.register(POOrder)
class POOrdersAdmin(admin.ModelAdmin):
    add_form_template = 'logistics/products_order.html'
    change_form_template = 'logistics/products_order.html'
    change_list_template = 'logistics/po_change_list.html'
    list_display = (
        'po_number',
        'supplier',
        'status',
        'created_at',
        'total_cost',
        'logistics_center_status',
        'total_arrived',
    )
    list_filter = (
        ('supplier__name', custom_titled_filter('Supplier Name')),
        (
            'purchaseorderproduct__product_id__brand__name',
            custom_titled_filter('Brand Name'),
        ),
        (POFilter),
        ('status', custom_titled_filter('Status')),
        ('created_at', admin.DateFieldListFilter),
    )
    actions = ['export_as_excel', 'send_again', 'quick_approve', 'cancel_po']
    search_fields = ['id', 'supplier__name', 'status']

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        # Get total cost from PurchaseOrderProducts
        total_cost_subquery = Subquery(
            PurchaseOrderProduct.objects.filter(purchase_order=OuterRef('id'))
            .values('purchase_order')
            .annotate(
                total_cost_db=Round(
                    Sum(
                        F('quantity_ordered')
                        * F('product_id__cost_price')
                        * (1 - Value(settings.TAX_PERCENT / 100))
                    )
                ),
            )
            .values('total_cost_db')
        )

        # Annotate total products arrived count
        queryset = queryset.annotate(
            total_arrived=Sum(
                Case(
                    When(
                        purchaseorderproduct__logisticscenterinboundreceiptline__purchase_order_product__purchase_order=F(
                            'id'
                        ),
                        then=F(
                            'purchaseorderproduct__logisticscenterinboundreceiptline__quantity_received'
                        ),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
        )

        return queryset.annotate(total_cost_db=total_cost_subquery)

    def total_cost(self, obj):
        return obj.total_cost_db

    total_cost.admin_order_field = 'total_cost_db'

    def total_arrived(self, obj):
        return obj.total_arrived or 0 if obj.status == 'APPROVED' else '-'

    total_arrived.admin_order_field = 'total_arrived'
    total_arrived.short_description = 'Total Arrived'

    def changelist_view(self, request):
        return super().changelist_view(
            request,
            extra_context={
                'title': 'Reports',
                'subtitle': 'PO Orders',
                'has_add_permission': False,
            },
        )

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """
        Customize the context passed to the change form template.
        """
        if request.GET.get('export'):
            workbook = self.get_order_workbook(object_id)
            output = io.BytesIO()
            workbook.save(output)
            output.seek(0)
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = (
                f'attachment; filename=PO_ORDER_{object_id}.xlsx'
            )
            response.write(output.getvalue())
            return response
        if extra_context is None:
            extra_context = {}
        instance: POOrder = self.get_object(request, object_id)
        po_product_variation_mapping = {}
        if instance:
            products = [*instance.products.values()]
            for product in products:
                variation_string = get_variations_string(product.get('variations'))
                product['variation_string'] = variation_string
                po_product_variation_mapping[str(product.get('id'))] = variation_string

        extra_context.update(
            {
                'product_instance': instance,
                'variations': po_product_variation_mapping,
                'tax_percent': settings.TAX_PERCENT,
            }
        )
        if instance and instance.status == POOrder.Status.APPROVED.name:
            self.change_form_template = 'logistics/change_products_order.html'
        else:
            self.change_form_template = 'logistics/products_order.html'
        return super().changeform_view(
            request, object_id, form_url, extra_context=extra_context
        )

    def get_urls(self):
        """
        Adding a url to show orders summary.
        """
        urls = super().get_urls()
        my_urls = [
            path('orders-summary/', self.get_orders_summary),
        ]
        return my_urls + urls

    def get_order_workbook(self, order_id):
        po_order = POOrder.objects.filter(id=order_id).first()
        po_order_supplier: Supplier = po_order.supplier
        workbook = Workbook()
        workbook.remove(workbook.active)

        po_worksheet = workbook.create_sheet('PO')
        po_products = []
        po_products_total_price = 0
        for order_product in po_order.products.all():
            product: Product = order_product.product_id
            brand: Brand = product.brand
            supplier: Supplier = product.supplier
            cost_price = round(product.cost_price * (1 - settings.TAX_PERCENT / 100), 2)
            total_price = cost_price * order_product.quantity_ordered
            po_products.append(
                {
                    'id': product.pk,
                    'name': product.name,
                    'category': getattr(product.categories.all().first(), 'name', ''),
                    'brand': brand.name,
                    'quantity': order_product.quantity_ordered,
                    'quantity_received': 0,
                    'sku': product.sku,
                    'barcode': product.reference,
                    'cost_price': cost_price,
                    'status': po_order.status,
                    'supplier': supplier.name,
                    'total_price': total_price,
                }
            )
            po_products_total_price += total_price
        po_products_columns = snake_to_title(list(po_products[0].keys()))
        po_worksheet.append(po_products_columns)
        for product in po_products:
            po_worksheet.append(list(product.values()))
        po_worksheet.append([])
        po_worksheet.append(['Description', 'Total Price'])
        po_worksheet.append([po_order.notes, po_products_total_price])

        orders_worksheet = workbook.create_sheet('Orders')
        order_products = []
        for order_product in EmployeeOrderProduct.objects.filter(
            product_id__product_id__pk__in=po_order.products.all().values_list(
                'product_id__pk', flat=True
            )
        ):
            order = order_product.order_id
            product = order_product.product_id.product_id
            order_products.append(
                {
                    'product_name': product.name,
                    'sku': product.sku,
                    'quantity': order_product.quantity,
                    'cost_price': round(
                        product.cost_price * (1 - settings.TAX_PERCENT / 100), 2
                    ),
                    'order_id': order.pk,
                    'employee_name': f'{order.campaign_employee_id.employee.full_name} - NKS',  # noqa: E501
                    'phone_number': order.phone_number,
                    'additional_phone_number': order.additional_phone_number,
                    'delivery_street': order.delivery_street,
                    'delivery_street_number': order.delivery_street_number,
                    'delivery_apartment_number': order.delivery_apartment_number,
                    'delivery_city': order.delivery_city,
                    'delivery_additional_details': order.delivery_additional_details,
                    'supplier_name': po_order_supplier.name,
                }
            )
        order_products_columns = snake_to_title(list(order_products[0].keys()))
        orders_worksheet.append(order_products_columns)
        for product in order_products:
            orders_worksheet.append(list(product.values()))

        return workbook

    def get_orders_summary(self, request, **kwargs):
        """
        Showing the orders summary with filtering and sorting.
        """
        search_form = SearchForm(request.GET)
        model_name = self.model._meta.model_name
        back = f'admin:{self.model._meta.app_label}_{model_name}_changelist'

        # Get filter parameters from GET request
        supplier = request.GET.get('supplier', '')
        brand = request.GET.get('brand', '')

        # Build the queryset with filters
        qs = (
            PurchaseOrderProduct.objects.values(
                'product_id__id',
                'product_id__supplier__name',
                'product_id__brand__name',
                'product_id__sku',
                'product_id__reference',
                'product_id__cost_price',
            )
            .annotate(
                total_ordered=Sum('quantity_ordered'),
            )
            .annotate(
                total_in_dc=Coalesce(
                    Sum(
                        Subquery(
                            LogisticsCenterInboundReceiptLine.objects.filter(
                                purchase_order_product=OuterRef('pk')
                            )
                            .values('purchase_order_product')
                            .order_by('purchase_order_product')
                            .annotate(total_in_dc=Sum('quantity_received'))
                            .values('total_in_dc')[:1],
                        )
                    ),
                    0,
                )
            )
            .annotate(
                total_in_transit=Sum('quantity_sent_to_logistics_center')
                - F('total_in_dc'),
                difference_to_order=F('total_ordered')
                - F('total_in_transit')
                - F('total_in_dc'),
            )
        )

        if search_form.is_valid():
            query = search_form.cleaned_data['query']
            if query:
                qs = qs.filter(
                    Q(product_id__supplier__name__icontains=query)
                    | Q(product_id__brand__name__icontains=query)
                    | Q(product_id__sku__icontains=query)
                    | Q(product_id__reference__icontains=query)
                )

        if supplier:
            qs = qs.filter(product_id__supplier__name__icontains=supplier)
        if brand:
            qs = qs.filter(product_id__brand__name__icontains=brand)

        return render(
            request,
            'logistics/po_summary.html',
            {
                'summary': list(qs),
                'back': back,
                'search_form': search_form,
                'filter': {
                    'supplier': supplier,
                    'brand': brand,
                },
            },
        )

    def create_product_row(self, order, product):
        record = [
            order.supplier.name,
            order.po_number,
            order.created_at.strftime('%d%m%Y'),
            exclude_taxes(product.total_cost),
            order.status,
            product.quantity_ordered,
            product.quantity_sent_to_logistics_center,
        ]
        return record

    def export_as_excel(self, request, queryset):
        """
        Export all queried orders as separate xlsx files, and if there are
        multiple files, download them all in a zip folder. If there's only one
        file, download it directly.
        """
        field_names = [
            'Supplier',
            'PO Number',
            'Creation Date',
            'Total Cost',
            'Status',
            'Quantity Ordered',
            'Quantity In Transit',
            'Quantity In DC',
        ]

        if queryset.count() == 1:
            # Handle single record case
            order = queryset.first()
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(field_names)

            for product in order.products.all():
                record = self.create_product_row(order, product)
                worksheet.append(record)

            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = (
                'attachment; filename=order_{}.xlsx'.format(order.po_number)
            )
            workbook.save(response)
            return response
        else:
            # Handle multiple records case
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                for order in queryset:
                    workbook = Workbook()
                    worksheet = workbook.active
                    worksheet.append(field_names)

                    for product in order.products.all():
                        record = self.create_product_row(order, product)
                        worksheet.append(record)
                    # Save workbook to a BytesIO object and add it to the zip file
                    file_buffer = io.BytesIO()
                    workbook.save(file_buffer)
                    file_buffer.seek(0)
                    zip_file.writestr(
                        'order_{}.xlsx'.format(order.po_number), file_buffer.read()
                    )

            response = HttpResponse(
                zip_buffer.getvalue(), content_type='application/zip'
            )
            response['Content-Disposition'] = 'attachment; filename=orders.zip'
            return response

    def send_again(self, request, queryset):
        send_purchaseorder_to_supplier.apply_async(
            (list(queryset.values_list('id', flat=True)),)
        )
        for purchase_order in queryset.all():
            update_order_products_po_status(purchase_order)
        self.message_user(
            request,
            ngettext(
                'Sent email to the supplier',
                'Sent emails to all the suppliers',
                queryset.count(),
            ),
            messages.SUCCESS,
        )

    def quick_approve(self, request, queryset):
        approved_count = 0
        errors = []

        # update status with calls to save for signals to be invoked
        for po in queryset.all():
            po.status = POOrder.Status.APPROVED.name
            po.save(update_fields=['status'])
            try:
                po.approve()
                approved_count += 1
            except ValidationError as ex:
                errors.append(ex.message)
            update_order_products_po_status(po)

        if approved_count > 0:
            self.message_user(
                request,
                ngettext(
                    'Purchase order is approved',
                    'Purchase orders are approved',
                    approved_count,
                ),
                messages.SUCCESS,
            )
        if len(errors) > 0:
            self.message_user(
                request,
                ', '.join(errors),
                messages.ERROR,
            )

    def cancel_po(self, request, queryset):
        queryset.update(status=POOrder.Status.CANCELLED.name)
        self.message_user(
            request,
            ngettext(
                'Purchase order is cancelled',
                'Purchase orders are cancelled',
                queryset.count(),
            ),
            messages.SUCCESS,
        )


class GuaranteedDeterministicChangeList(ChangeList):
    """
    This is a ChangeList descendant which removes the deterministic order logic
    since we want to display aggregated data in change lists, which the
    original logic deems non-deterministcally-ordered and then adds ordering
    (and a groups) by the main object pk, which then ruins our aggregation.
    Do not use this for normal admins!
    """

    def _get_deterministic_ordering(self, ordering):
        return list(ordering)


@admin.register(EmployeeOrderProduct)
class OrderSummaryAdmin(admin.ModelAdmin):
    list_display_links = None
    ordering = (
        Coalesce(
            F('product_id__product_id__bundled_items__product__sku'),
            F('product_id__product_id__sku'),
        ),
    )
    list_filter = (
        (
            'product_id__employee_group_campaign_id__campaign__status',
            custom_titled_filter('Campaign Status'),
        ),
        'product_id__product_id__supplier',
        'product_id__product_id__brand',
        'product_id__product_id__product_type',
        'product_id__product_id__product_kind',
        'product_id__employee_group_campaign_id__campaign__organization__name',
        'product_id__employee_group_campaign_id__campaign__tags',
    )
    search_fields = (
        'product_sku',
        'product_supplier',
        'product_brand',
    )
    actions = ('create_po', 'export_as_xlsx')

    change_list_template = 'logistics/order_summary_change_list.html'

    def get_list_display(self, request):
        list_display = [
            'product_supplier',
            'product_brand',
            'product_sku',
            'product_kind',
        ]

        variations = self.get_queryset(request=request).values('variations')
        extra_keys = self.get_extra_keys(variations=variations)

        list_display.extend(extra_keys)
        list_display.extend(
            [
                'product_name',
                'product_reference',
                'total_ordered',
                'product_cost_price',
                'product_quantity',
                'sent_to_approve',
                'in_transit_stock',
                'dc_stock',
                'product_snapshot_stock',
                'difference_to_order',
                'product_snapshot_stock_date_time',
            ]
        )

        for key in extra_keys:
            self.create_dynamic_column(key)

        return list_display

    def get_extra_keys(self, variations):
        unique_keys = set()
        for extras in variations:
            if isinstance(extras, dict):
                variation_data = extras.values()
                for variation in variation_data:
                    if isinstance(variation, dict):
                        unique_keys.update(variation.keys())
        unique_keys = [key.replace(' ', '_') for key in unique_keys]
        return list(unique_keys)

    def create_dynamic_column(self, key):
        def dynamic_column(admin_self, obj):
            merged = obj.get('merged_variations', {})
            return merged.get(key, '')

        dynamic_column.short_description = key.replace('_', ' ')
        setattr(OrderSummaryAdmin, key, dynamic_column)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(
            order_id__status__in=(
                Order.OrderStatusEnum.PENDING.name,
                Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
            ),
        )
        # Define subqueries for sent_to_dc, quantity_ordered, and dc_stock.
        sent_to_dc_subquery = Subquery(
            PurchaseOrderProduct.objects.filter(
                product_id_id=Coalesce(
                    OuterRef('product_id__product_id__bundled_items__product__id'),
                    OuterRef('product_id__product_id_id'),
                )
            )
            .values('product_id_id')
            .annotate(sent_to_dc=Sum(F('quantity_sent_to_logistics_center')))
            .values('sent_to_dc')[:1]
        )
        quantity_ordered_subquery = Subquery(
            PurchaseOrderProduct.objects.filter(
                purchase_order__status=PurchaseOrder.Status.SENT_TO_SUPPLIER.name,
                product_id_id=Coalesce(
                    OuterRef('product_id__product_id__bundled_items__product__id'),
                    OuterRef('product_id__product_id_id'),
                ),
            )
            .values('product_id_id')
            .annotate(quantity_ordered=Sum(F('quantity_ordered')))
            .values('quantity_ordered')[:1]
        )
        dc_stock_subquery = Subquery(
            PurchaseOrderProduct.objects.filter(
                product_id_id=Coalesce(
                    OuterRef('product_id__product_id__bundled_items__product__id'),
                    OuterRef('product_id__product_id_id'),
                )
            )
            .values('product_id_id')
            .annotate(
                dc_stock=Sum(F('logisticscenterinboundreceiptline__quantity_received'))
            )
            .values('dc_stock')[:1]
        )

        # Annotate base fields.
        base_qs = qs.annotate(
            product_supplier=Coalesce(
                F('product_id__product_id__bundled_items__product__supplier__name'),
                F('product_id__product_id__supplier__name'),
            ),
            product_sku=Coalesce(
                F('product_id__product_id__bundled_items__product__sku'),
                F('product_id__product_id__sku'),
            ),
            product_kind=Coalesce(
                F('product_id__product_id__bundled_items__product__product_kind'),
                F('product_id__product_id__product_kind'),
            ),
            product_name=Coalesce(
                F('product_id__product_id__bundled_items__product__name'),
                F('product_id__product_id__name'),
            ),
            base_ordered_quantity=F('quantity')
            * Coalesce(F('product_id__product_id__bundled_items__quantity'), Value(1)),
            sent_to_dc=Coalesce(sent_to_dc_subquery, 0),
            dc_stock=Coalesce(dc_stock_subquery, 0),
        )
        self.unmerged_qs = base_qs

        # Group by product_supplier and product_sku.
        grouped_qs = (
            base_qs.values('product_supplier', 'product_sku')
            .annotate(
                total_ordered=Sum('base_ordered_quantity'),
                sum_sent_to_dc=Max('sent_to_dc'),
                sum_dc_stock=Max('dc_stock'),
                product_brand=Coalesce(
                    F('product_id__product_id__bundled_items__product__brand__name'),
                    F('product_id__product_id__brand__name'),
                ),
                product_reference=Coalesce(
                    F('product_id__product_id__bundled_items__product__reference'),
                    F('product_id__product_id__reference'),
                ),
                product_cost_price=Coalesce(
                    F('product_id__product_id__bundled_items__product__cost_price'),
                    F('product_id__product_id__cost_price'),
                ),
                product_quantity=Coalesce(
                    F(
                        'product_id__product_id__bundled_items__product__product_quantity'
                    ),
                    F('product_id__product_id__product_quantity'),
                ),
                product_kind=Coalesce(
                    F('product_id__product_id__bundled_items__product__product_kind'),
                    F('product_id__product_id__product_kind'),
                ),
                product_name=Coalesce(
                    F('product_id__product_id__bundled_items__product__name'),
                    F('product_id__product_id__name'),
                ),
                product_pk=Coalesce(
                    F('product_id__product_id__bundled_items__product__id'),
                    F('product_id__product_id_id'),
                ),
                product_snapshot_stock=Coalesce(
                    F(
                        'product_id__product_id__bundled_items__product__logistics_snapshot_stock_line__quantity'
                    ),
                    F(
                        'product_id__product_id__logistics_snapshot_stock_line__quantity'
                    ),
                ),
                product_snapshot_stock_date_time=Coalesce(
                    F(
                        'product_id__product_id__bundled_items__product__logistics_snapshot_stock_line__stock_snapshot__snapshot_date_time'
                    ),
                    F(
                        'product_id__product_id__logistics_snapshot_stock_line__stock_snapshot__snapshot_date_time'
                    ),
                ),
                sent_to_approve=Coalesce(quantity_ordered_subquery, 0),
            )
            .annotate(
                dc_stock=F('sum_dc_stock'),
                in_transit_stock=F('sum_sent_to_dc') - F('sum_dc_stock'),
                difference_to_order=F('total_ordered')
                - F('sent_to_dc')
                - F('sent_to_approve'),
                pk=F('product_pk'),
            )
        )
        final_keys = [
            'product_supplier',
            'product_sku',
            'total_ordered',
            'sum_sent_to_dc',
            'sum_dc_stock',
            'product_brand',
            'product_reference',
            'product_cost_price',
            'product_quantity',
            'product_kind',
            'product_name',
            'sent_to_approve',
            'product_pk',
            'product_snapshot_stock',
            'product_snapshot_stock_date_time',
            'dc_stock',
            'in_transit_stock',
            'difference_to_order',
            'pk',
            'variations',
        ]
        # Preserve extra variation keys as before.
        keys = self.get_extra_keys(variations=grouped_qs.values('variations'))
        grouped_qs = grouped_qs.annotate(**{key: Value('') for key in keys})
        return grouped_qs.values(*final_keys)

    def get_changelist(self, request, **kwargs):
        return GuaranteedDeterministicChangeList

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            cl = response.context_data.get('cl')
            if not cl:
                return response

            # Compute extra keys from variations (using the base queryset)
            extra_keys = self.get_extra_keys(
                variations=self.get_queryset(request).values('variations')
            )

            for row in cl.result_list:
                supplier = row.get('product_supplier')
                sku = row.get('product_sku')
                merged_variations = {}
                duplicates = self.unmerged_qs.filter(
                    product_supplier=supplier, product_sku=sku
                ).values_list('variations', flat=True)
                for var in duplicates:
                    if not var:
                        continue
                    for k, v in var.items():
                        merged_variations[k] = v

                # Optionally, append variation text to the SKU for display
                variations_text = []
                for key, value in merged_variations.items():
                    variation_kind = get_variation_type(
                        variation=key
                    )  # your helper function
                    if variation_kind == 'COLOR':
                        variations_text.insert(0, str(value)[:2])
                    elif variation_kind == 'TEXT':
                        variations_text.append(str(value)[:1])

                variations = row['variations']
                if variations:
                    variations_text = []
                    for key, value in variations.items():
                        row[key.replace(' ', '_')] = value
                        variation_kind = get_variation_type(variation=key)
                        if variation_kind == 'COLOR':
                            variations_text.insert(0, str(value[:2]))
                        elif variation_kind == 'TEXT':
                            variations_text.append(str(value[:1]))

                    row['product_sku'] = str(row['product_sku']) + ''.join(
                        variations_text
                    )

                # Ensure every extra dynamic key is present in the row, even if empty.
                for key in extra_keys:
                    if key not in row:
                        row[key] = ''
        except Exception as e:
            print(f'Error merging variations: {e}')
        return response

    @staticmethod
    def parse_variations(order_summary):
        color_variations = []
        text_variations = []
        if order_summary['variations']:
            for variation_type, variation_value in order_summary['variations'].items():
                variation_instance = Variation.objects.filter(
                    Q(site_name_he=variation_type) | Q(site_name_en=variation_type)
                ).first()
                if variation_instance:
                    if (
                        Variation.VariationKindEnum.COLOR.name
                        == variation_instance.variation_kind
                    ):
                        color_variations.append(variation_value)
                    elif (
                        Variation.VariationKindEnum.TEXT.name
                        == variation_instance.variation_kind
                    ):
                        text_variations.append(variation_value)
        return '|'.join([', '.join(color_variations), ', '.join(text_variations)])

    def action_checkbox(self, obj):
        unique_id = str(obj.get('pk', ''))
        """
        An override of the ancestor method to use a non-pk field and read it
        from a dictionary and not only as an attribute
        """
        attrs = {
            'class': 'action-select',
            'aria-label': format_html(
                _('Select this object for an action - {}'), unique_id
            ),
        }
        checkbox = forms.CheckboxInput(attrs, lambda value: False)
        return checkbox.render(helpers.ACTION_CHECKBOX_NAME, str(obj['pk']))

    def create_po(self, request, queryset):
        product_kinds = queryset.values_list('product_kind', flat=True)
        if 'MONEY' in product_kinds and len(set(product_kinds)) > 1:
            self.message_user(
                request, 'Please select same kind of products', level=messages.ERROR
            )
            return

        queryset = queryset.filter(difference_to_order__gt=0)
        params = {}
        if queryset.first():
            params = {
                'supplierName': queryset.first()['product_supplier'],
                'productSkus': ','.join(
                    [
                        f'{p["product_sku"]}|||{max(0, p["difference_to_order"])}'
                        f'|||{p["product_sku"]}{get_variations_string(p.get("variations"))}|||{p["pk"]}'  # noqa: E501
                        for p in queryset.all()
                    ]
                ),
            }

        add_page_url = reverse('admin:logistics_poorder_add')
        add_page_url = f'{add_page_url}?{urlencode(params)}'
        return redirect(add_page_url)

    def export_as_xlsx(self, request, queryset):
        # using the inner query since it can be pickled to recreate the
        # queryset (celery is in charge of pickling here), based on docs -
        # https://docs.djangoproject.com/en/5.1/ref/models/querysets/#pickling-querysets
        export_order_summaries_as_xlsx_task.apply_async(
            (
                queryset.query,
                request.user.pk,
                request.user.email,
                drf_reverse('download_export_file_view', request=request),
            )
        )

        self.message_user(
            request,
            (
                'Exporting order summaries, file will be sent to '
                f'"{request.user.email}" when ready'
            ),
            messages.SUCCESS,
        )

    def product_supplier(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    product_supplier.short_description = 'Supplier'

    def product_brand(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    product_brand.short_description = 'Brand'

    def product_sku(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    def product_kind(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    def color_variations(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    def text_variations(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    product_sku.short_description = 'Sku'

    def product_name(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    product_name.short_description = 'Name'

    def product_reference(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    product_reference.short_description = 'Barcode'

    def total_ordered(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    total_ordered.short_description = 'Total Ordered'

    def product_cost_price(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    product_cost_price.short_description = 'Cost Price'

    def product_quantity(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    product_quantity.short_description = 'Saved Stock'

    def in_transit_stock(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    in_transit_stock.short_description = 'In Transit Stock'

    def dc_stock(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    dc_stock.short_description = 'DC Stock'

    def product_snapshot_stock(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    product_snapshot_stock.short_description = 'DC Snapshot Stock'

    def product_snapshot_stock_date_time(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    product_snapshot_stock_date_time.short_description = 'DC Snapshot Stock Date Time'

    def difference_to_order(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    difference_to_order.short_description = 'Difference To Order'

    def sent_to_approve(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return obj.get('sent_to_approve', 0)

    sent_to_approve.short_description = 'Sent to Approve'

    class Media:
        js = ('js/order_summary.js',)
