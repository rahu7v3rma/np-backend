import io
from urllib.parse import urlencode
import zipfile

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.views.main import ChangeList
from django.db.models import F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _, ngettext
from openpyxl import Workbook
from rest_framework.reverse import reverse as drf_reverse

from campaign.models import Order

from .forms import SearchForm
from .models import (
    EmployeeOrderProduct,
    LogisticsCenterInboundReceiptLine,
    POOrder,
    PurchaseOrderProduct,
)
from .tasks import (
    export_order_summaries_as_xlsx_task,
    send_purchaseorder_to_supplier,
)


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
            f'{str(data_list[i:i + self.chunk_size][0][0])}-{str(data_list[i:i + self.chunk_size][-1][0])}'  # noqa: E501
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
    list_display = ('po_number', 'supplier', 'status', 'created_at', 'total_cost')
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

        total_cost_subquery = Subquery(
            PurchaseOrderProduct.objects.filter(purchase_order=OuterRef('id'))
            .values('purchase_order')
            .annotate(
                total_cost_db=Sum(F('quantity_ordered') * F('product_id__cost_price'))
            )
            .values('total_cost_db')
        )

        return queryset.annotate(total_cost_db=total_cost_subquery)

    def total_cost(self, obj):
        return obj.total_cost

    total_cost.admin_order_field = 'total_cost_db'

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
        if extra_context is None:
            extra_context = {}

        instance: POOrder = self.get_object(request, object_id)

        extra_context.update({'product_instance': instance})
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
            product.total_cost,
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
        # update status with calls to save for signals to be invoked
        for po in queryset.all():
            po.status = POOrder.Status.APPROVED.name
            po.save(update_fields=['status'])

        self.message_user(
            request,
            ngettext(
                'Purchase order is approved',
                'Purchase orders are approved',
                queryset.count(),
            ),
            messages.SUCCESS,
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
    list_display = (
        'product_supplier',
        'product_brand',
        'product_sku',
        'product_reference',
        'total_ordered',
        'product_cost_price',
        'product_quantity',
        'in_transit_stock',
        'dc_stock',
        'difference_to_order',
    )
    list_display_links = None
    ordering = ('product_id__product_id__sku',)
    list_filter = (
        'product_id__product_id__supplier',
        'product_id__product_id__brand',
        'product_id__product_id__product_type',
        'product_id__product_id__product_kind',
        'product_id__employee_group_campaign_id__campaign__organization__name',
    )
    search_fields = (
        'product_sku',
        'product_supplier',
        'product_brand',
    )
    actions = ('create_po', 'export_as_xlsx')

    change_list_template = 'logistics/order_summary_change_list.html'

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(order_id__status=Order.OrderStatusEnum.PENDING.name)

        sent_to_dc_subquery = Subquery(
            PurchaseOrderProduct.objects.filter(product_id_id=OuterRef('product_pk'))
            .values('product_id_id')
            .annotate(
                sent_to_dc=Sum(F('quantity_sent_to_logistics_center')),
            )
            .values('sent_to_dc')
        )
        dc_stock_subquery = Subquery(
            PurchaseOrderProduct.objects.filter(product_id_id=OuterRef('product_pk'))
            .values('product_id_id')
            .annotate(
                dc_stock=Sum(F('logisticscenterinboundreceiptline__quantity_received')),
            )
            .values('dc_stock')
        )

        qs = (
            qs.annotate(
                product_pk=F('product_id__product_id_id'),
                product_supplier=F('product_id__product_id__supplier__name'),
                product_brand=F('product_id__product_id__brand__name'),
                product_sku=F('product_id__product_id__sku'),
                product_reference=F('product_id__product_id__reference'),
                product_cost_price=F('product_id__product_id__cost_price'),
                product_quantity=F('product_id__product_id__product_quantity'),
            )
            .values(
                'product_pk',
                'product_supplier',
                'product_brand',
                'product_sku',
                'product_reference',
                'product_cost_price',
                'product_quantity',
            )
            .annotate(
                total_ordered=Sum(F('quantity')),
                sent_to_dc=Coalesce(sent_to_dc_subquery, 0),
                dc_stock=Coalesce(dc_stock_subquery, 0),
            )
            .annotate(
                in_transit_stock=F('sent_to_dc') - F('dc_stock'),
                difference_to_order=F('total_ordered')
                - F('in_transit_stock')
                - F('dc_stock'),
                # the pk value is used by the action checkboxes logic
                pk=F('product_sku'),
            )
        )

        return qs

    def get_changelist(self, request, **kwargs):
        return GuaranteedDeterministicChangeList

    def action_checkbox(self, obj):
        """
        An override of the ancestor method to use a non-pk field and read it
        from a dictionary and not only as an attribute
        """
        attrs = {
            'class': 'action-select',
            'aria-label': format_html(_('Select this object for an action - {}'), obj),
        }
        checkbox = forms.CheckboxInput(attrs, lambda value: False)
        return checkbox.render(helpers.ACTION_CHECKBOX_NAME, str(obj['pk']))

    def create_po(self, request, queryset):
        params = {
            'supplierName': queryset.first()['product_supplier'],
            'productSkus': ','.join(
                [
                    f'{p["product_sku"]}|||{max(0, p["difference_to_order"])}'
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

    product_sku.short_description = 'Sku'

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

    def difference_to_order(self, obj):
        # this method isn't invoked, but is required for django to validate the
        # list_display fields. it returns a static value so as to not confuse
        # if the value ever needs to be changed (all values are computed in the
        # queryset above)
        return ''

    difference_to_order.short_description = 'Difference To Order'
