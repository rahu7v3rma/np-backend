from functools import update_wrapper
from io import BytesIO
import logging
from typing import Any

from django.contrib import admin, messages
from django.db.models import (
    Count,
    ExpressionWrapper,
    F,
    FilteredRelation,
    FloatField,
    Q,
    Value,
)
from django.db.models.functions import Cast, Round
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.datastructures import MultiValueDict
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill

from inventory.models import Product
from lib.admin import ImportableExportableAdmin

from .admin_actions import CampaignActionsMixin, OrderActionsMixin
from .admin_forms import EmployeeForm, ImportPricelistForm, OrderProductInlineFormset
from .admin_views import (
    CampaignCreationWizard,
    CampaignImpersonateView,
    CampaignInvitationView,
)
from .forms import EmployeeGroupForm
from .models import (
    Campaign,
    CampaignEmployee,
    Employee,
    EmployeeGroup,
    EmployeeGroupCampaign,
    Order,
    OrderProduct,
    Organization,
    OrganizationProduct,
)
from .utils import format_with_none_replacement


logger = logging.getLogger(__name__)


class EmployeeGroupInline(admin.TabularInline):
    model = EmployeeGroup
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(ImportableExportableAdmin):
    inlines = (EmployeeGroupInline,)

    fieldsets = [
        (
            None,
            {
                'fields': (
                    'name',
                    'manager_full_name',
                    'manager_phone_number',
                    'manager_email',
                    'logo_image',
                ),
            },
        ),
        ('ORGANIZATION PRODUCTS', {'fields': ('organization_products_link',)}),
    ]
    readonly_fields = ('organization_products_link',)

    list_display = (
        'name',
        'manager_full_name',
        'number_of_employees',
    )
    add_form_template = 'admin/organization_form.html'
    change_form_template = 'campaign/change_organization_form.html'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(employees_count=Count('employeegroup__employee'))
        return qs

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj:
            self.organization_id = obj.id
        else:
            self.organization_id = 0
        return form

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['organization_id'] = object_id
        extra_context['change'] = True

        if object_id and request.method == 'POST' and 'xlsx' in request.FILES:
            info = self.opts.app_label, self.opts.model_name
            viewname = 'admin:%s_%s_change' % info

            try:
                form = ImportPricelistForm(request.POST, request.FILES)
                if not form.is_valid():
                    self.message_user(
                        request,
                        'Imported pricelist file is invalid.',
                        level=messages.ERROR,
                    )
                    return redirect(reverse(viewname, args=(object_id,)))

                xlsx = form.clean().get('xlsx')
                workbook = load_workbook(xlsx)
                xlsx = workbook.active

                required_column_indices = {
                    'sku': None,
                    'organization price': None,
                }

                # read the first (title) row and fill required column indices
                for row in xlsx.iter_rows(max_row=1, max_col=10, values_only=True):
                    for i, cell in enumerate(row):
                        if cell in required_column_indices:
                            required_column_indices[cell] = i

                    break

                # if any required column was not found fail
                if any(v is None for v in required_column_indices.values()):
                    self.message_user(
                        request,
                        'An error occured while importing pricelist: '
                        'Imported sheet columns are invalid, '
                        'Download the sample by exporting pricelist.',
                        level=messages.ERROR,
                    )
                    return redirect(reverse(viewname, args=(object_id,)))

                org = Organization.objects.filter(pk=object_id).first()
                success = []
                errors = []

                for index, row in enumerate(
                    xlsx.iter_rows(min_row=2, max_col=10, values_only=True)
                ):
                    row_num = index + 2

                    empty_row = all(cell is None for cell in row)
                    if empty_row:
                        continue

                    # get product current values so that we don't depend on
                    # any value set in the excel file
                    sku = row[required_column_indices['sku']]
                    product = Product.objects.filter(sku=sku).first()

                    if not product:
                        errors.append(f'Could not find product with SKU "{sku}"')
                        continue

                    google_price = product.google_price
                    # total_cost = product.total_cost

                    org_price = row[required_column_indices['organization price']]
                    if org_price is not None:
                        if not isinstance(org_price, (float, int)):
                            errors.append(
                                f'Organization price is invalid for SKU ({sku}) at '
                                f'row number {row_num}.'
                            )
                            continue
                        else:
                            org_price = int(org_price)

                            # TODO: re-enable as a warning which requires
                            # confirmation to continue
                            # # validate organization price is not lower than total cost
                            # if org_price < total_cost:
                            #     errors.append(
                            #         'Organization price cannot be less than product '
                            #         f'total cost for SKU ({sku}) at row number '
                            #         f'{row_num}.'
                            #     )
                            #     continue

                    # validate organization price is not higher than google price
                    if (
                        google_price is not None
                        and org_price is not None
                        and org_price > google_price
                    ):
                        errors.append(
                            'Organization price cannot be higher than product google '
                            f'price for SKU ({sku}) at row number {row_num}.'
                        )
                        continue

                    org_product = OrganizationProduct.objects.filter(
                        organization=org,
                        product=product,
                    ).first()

                    # there are two cases - one is organization price is set to
                    # any value in which organization product must exist or be
                    # created, and one is organization price is None in which
                    # case if an organization product object exists we should
                    # remove it as the price was unset
                    if org_price is not None:
                        if org_product:
                            org_product.price = org_price
                            org_product.save()
                        else:
                            OrganizationProduct.objects.create(
                                organization=org,
                                product=product,
                                price=org_price,
                            )

                        success.append(sku)
                    elif org_price is None and org_product:
                        org_product.delete()
                        success.append(sku)

                if success:
                    message = 'Success updating organization price for products: '
                    message += ', '.join(success)
                    self.message_user(request, message, level=messages.SUCCESS)

                if errors:
                    errors.insert(
                        0, 'Errors updating organization price for following products:'
                    )
                    for message in errors:
                        self.message_user(request, message, level=messages.ERROR)

                return redirect(reverse(viewname, args=(object_id,)))
            except Exception as ex:
                logger.error(
                    f'An unknown error has occurred while importing prices: {ex}'
                )
                message = 'An unknown error has occurred while importing prices'
                self.message_user(request, message, level=messages.ERROR)
                return redirect(reverse(viewname, args=(object_id,)))

        return super(OrganizationAdmin, self).change_view(
            request, object_id, form_url, extra_context
        )

    def get_urls(self):
        urls = super().get_urls()
        app = self.opts.app_label
        model = self.opts.model_name
        custom_urls = [
            path(
                '<path:object_id>/export-pricelist/',
                self.export_pricelist,
                name=f'{app}_{model}_export_pricelist',
            ),
        ]
        return custom_urls + urls

    def export_pricelist(self, request, object_id):
        app = self.model._meta.app_label
        model = self.model._meta.model_name
        change_view = f'admin:{app}_{model}_change'

        try:
            org = Organization.objects.filter(pk=object_id).first()

            export_plain_columns = [
                'name_en',
                'name_he',
                'sku',
                'total_cost',
                'cost_price',
                'sale_price',
                'google_price',
                'product_kind',
                'supplier__name',
            ]

            export_calculated_columns = dict(
                organization_price=Cast(
                    'org_product__price', output_field=FloatField()
                ),
                bottom_margin=Round(
                    ExpressionWrapper(
                        F('cost_price') * Value(1.1), output_field=FloatField()
                    ),
                    2,
                ),
                top_margin=Round(
                    ExpressionWrapper(
                        F('cost_price') * Value(1.2), output_field=FloatField()
                    ),
                    2,
                ),
            )

            export_forumla_columns = {
                'profit': (
                    '=IF(ISBLANK($H{row_num}), "", ROUND(($H{row_num} '
                    '- $E{row_num}) / $E{row_num}, 2))'
                )
            }

            # used for forcing number formats on specific columns
            export_column_number_format = {
                'sku': '@',
                'profit': '0.00%',
            }

            products = Product.objects.annotate(
                org_product=FilteredRelation(
                    'organizationproduct',
                    condition=Q(organizationproduct__organization=org),
                ),
            ).values(*export_plain_columns, **export_calculated_columns)

            columns = (
                [c.replace('_', ' ') for c in export_plain_columns]
                + [c.replace('_', ' ') for c in export_calculated_columns.keys()]
                + list(export_forumla_columns.keys())
            )

            workbook = Workbook()
            xlsx = workbook.active
            xlsx.append(columns)

            for product_idx, product in enumerate(products):
                row = list(product.values())

                # add formula columns
                for formula in export_forumla_columns.values():
                    # this would be much easier if we could set a formula value
                    # to a range of cells, but it seems we can't so each
                    # cell formula should point to the correct row number
                    row.append(formula.format(row_num=product_idx + 2))

                xlsx.append(row)

            # force number formats where needed
            for k, v in export_column_number_format.items():
                # find column name in columns list and add 1 since worksheet
                # iteration values are 1-based
                column_index = columns.index(k) + 1

                for col in xlsx.iter_cols(
                    min_row=2, min_col=column_index, max_col=column_index
                ):
                    for cell in col:
                        cell.number_format = v

            red_fill = PatternFill(
                start_color='FF0000', end_color='FF0000', fill_type='solid'
            )
            green_fill = PatternFill(
                start_color='00FF00', end_color='00FF00', fill_type='solid'
            )
            no_fill = PatternFill(fill_type=None)

            # add conditional fill to organization price column values - no
            # fill for blank values, green fill if the value is between the
            # bottom and top margin and red fill otherwise ('notBetween'
            # operator did not work for some reason, so there's greaterThan and
            # lessThan instead)
            xlsx.conditional_formatting.add(
                f'H2:H{len(products) + 1}',
                CellIsRule(
                    operator='equal',
                    formula=['""'],
                    stopIfTrue=True,
                    fill=no_fill,
                ),
            )
            xlsx.conditional_formatting.add(
                f'H2:H{len(products) + 1}',
                CellIsRule(
                    operator='lessThan',
                    formula=['$I2'],
                    stopIfTrue=True,
                    fill=red_fill,
                ),
            )
            xlsx.conditional_formatting.add(
                f'H2:H{len(products) + 1}',
                CellIsRule(
                    operator='greaterThan',
                    formula=['$J2'],
                    stopIfTrue=True,
                    fill=red_fill,
                ),
            )
            xlsx.conditional_formatting.add(
                f'H2:H{len(products) + 1}',
                CellIsRule(
                    operator='between',
                    formula=['$I2', '$J2'],
                    stopIfTrue=True,
                    fill=green_fill,
                ),
            )

            output = BytesIO()
            workbook.save(output)
            output.seek(0)
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = (
                f'attachment; filename={org.name}_pricelist.xlsx'
            )
            response.write(output.getvalue())
            return response
        except Exception as ex:
            logger.error(
                'An unknown error has occurred while exporting organization '
                f'prices: {ex}'
            )
            message = (
                'An unknown error has occurred while exporting organization prices'
            )
            self.message_user(request, message, level=messages.ERROR)
            return redirect(reverse(change_view, args=(object_id,)))

    def organization_products_link(self, obj):
        count = obj.products.count()

        organization_product_changelist_url = reverse(
            'admin:campaign_organizationproduct_changelist'
        )
        search_params = urlencode({'organization__id__exact': obj.id})

        return mark_safe(
            f'<a href="{organization_product_changelist_url}?{search_params}">'
            f'Total products: {count}</a>'
        )

    def number_of_employees(self, obj):
        return obj.employees_count

    number_of_employees.admin_order_field = 'employees_count'

    organization_products_link.short_description = 'Organization products'


@admin.register(Employee)
class EmployeeAdmin(ImportableExportableAdmin):
    list_display = (
        'first_name',
        'last_name',
        'employee_group',
        'organization',
    )
    list_filter = ('employee_group__organization',)
    actions = ['export_as_xlsx']
    form = EmployeeForm
    change_form_template = 'admin/employee_form.html'
    exclude = ('otp_secret',)

    export_fields = (
        'employee_group__name',
        'first_name_en',
        'first_name_he',
        'last_name_en',
        'last_name_he',
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
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'import-data/organization/<int:organization_id>/',
                self.admin_site.admin_view(self.import_xlsx),
                name='import_data_organization_employees',
            ),
        ]
        return custom_urls + urls

    def import_parse_field(
        self,
        name: str,
        value: str,
        extra_params: dict[str, Any],
        extra_files: MultiValueDict,
    ):
        if name == 'employee_group':
            organization = Organization.objects.get(id=extra_params['organization_id'])
            return EmployeeGroup.objects.get(name=value, organization=organization)

        return super().import_parse_field(name, value, extra_params, extra_files)


class EmployeeInline(admin.TabularInline):
    model = Employee
    extra = 1
    exclude = ('otp_secret',)


@admin.register(EmployeeGroup)
class EmployeeGroupAdmin(admin.ModelAdmin):
    form = EmployeeGroupForm
    list_display = ('name', 'campaign_names', 'organization', 'total_employees')
    inlines = [EmployeeInline]


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin, CampaignActionsMixin):
    actions = [
        'activate_campaign',
        'finish_campaign',
        'export_orders_as_xlsx',
        'resend_invitation',
    ]

    list_display = (
        'name',
        'duplicate_link',
        'status',
        'total_employees',
        'ordered_number',
        'ordered_percentage',
        'organization_link',
        'employee_site_link',
    )

    change_list_template = 'campaign/campaign_change_list.html'

    def employee_site_link(self, obj):
        href_str_list = []
        egc_obs = EmployeeGroupCampaign.objects.filter(campaign=obj)
        for egc in egc_obs:
            href_str_list.append(
                f'{egc.employee_group.name} - {egc.employee_site_link}'
            )

        link = '    --------    '.join(href_str_list)
        return format_html(
            '<a href="#" onclick="copyToClipboard(\'{0}\');'
            'return false;">Copy link</a>'
            '<input type="hidden" class="copy-link-input" value="{0}">',
            link,
        )

    def get_urls(self):
        app_label = self.opts.app_label
        model_name = self.opts.model_name
        return [
            path(
                '',
                update_wrapper(
                    self.admin_site.admin_view(self.changelist_view),
                    self.changelist_view,
                ),
                name=f'{app_label}_{model_name}_changelist',
            ),
            path(
                'add/',
                self.admin_site.admin_view(CampaignCreationWizard.as_view()),
                name=f'{app_label}_{model_name}_add',
            ),
            path(
                '<path:object_id>/change/',
                self.admin_site.admin_view(self.change_view),
                name=f'{app_label}_{model_name}_change',
            ),
            path(
                'edit/',
                self.admin_site.admin_view(CampaignCreationWizard.as_view()),
                name=f'{app_label}_{model_name}_edit',
            ),
            path(
                '<path:object_id>/status/',
                self.admin_site.admin_view(self.status_view),
                name=f'{app_label}_{model_name}_change',
            ),
            path(
                '<int:campaign_id>/preview/<int:employee_group_campaign_id>',
                CampaignImpersonateView.as_view(),
                name='campaign_preview_view',
            ),
            path(
                '<int:campaign_id>/impersonate/<int:campaign_employee_id>',
                CampaignImpersonateView.as_view(),
                name='campaign_impersonate_view',
            ),
            path(
                '<int:campaign_id>/invitation',
                CampaignInvitationView.as_view(),
                name='campaign_invitation_view',
            ),
        ]

    def status_view(self, request, object_id):
        campaign = Campaign.objects.get(pk=object_id)

        if campaign.status in (
            Campaign.CampaignStatusEnum.PENDING.name,
            Campaign.CampaignStatusEnum.OFFER.name,
        ):
            status = (
                EmployeeGroupCampaign.objects.filter(campaign_id=object_id)
                .select_related('employee_group')
                .values(
                    employee_group_name=F('employee_group__name'),
                    employee_first_name=F('employee_group__employee__first_name'),
                    employee_last_name=F('employee_group__employee__last_name'),
                )
            )
        else:
            raw_status = (
                CampaignEmployee.objects.filter(campaign_id=object_id)
                .select_related('employee', 'employee__employee_group', 'order')
                .annotate(
                    pending_order=FilteredRelation(
                        'order',
                        condition=Q(order__status=Order.OrderStatusEnum.PENDING.name),
                    ),
                )
                .values(
                    campaign_employee_id=F('pk'),
                    employee_group_name=F('employee__employee_group__name'),
                    employee_first_name=F('employee__first_name'),
                    employee_last_name=F('employee__last_name'),
                    order_id=F('pending_order__pk'),
                    ordered_products=F(
                        'pending_order__orderproduct__product_id__product_id__name'
                    ),
                )
            )

            # we want to concat order products so we can display all ordered
            # products in a single cell in the status form. sadly, string_agg
            # is only supported with postgresql in django
            concat_products_status = {}
            for rs in raw_status:
                key = f'{rs["campaign_employee_id"]}_{rs["order_id"]}'

                if key in concat_products_status:
                    concat_products_status[key]['ordered_products'].append(
                        rs['ordered_products']
                    )
                else:
                    rs['ordered_products'] = (
                        [rs['ordered_products']] if rs['ordered_products'] else []
                    )
                    concat_products_status[key] = rs

            for k in concat_products_status:
                concat_products_status[k]['ordered_products'] = ', '.join(
                    concat_products_status[k]['ordered_products']
                )

            status = concat_products_status.values()

        context = {
            **self.admin_site.each_context(request),
            'opts': self.opts,
            'object_id': object_id,
            'title': 'Campaign Status',
            'subtitle': campaign.name,
            'status': status,
            'employee_groups': campaign.employeegroupcampaign_set.select_related(
                'employee_group'
            ).values('id', employee_group_name=F('employee_group__name')),
            'campaign_active': campaign.status
            == Campaign.CampaignStatusEnum.ACTIVE.name,
            'campaign_code': campaign.code,
        }
        return TemplateResponse(request, 'campaign/status_form.html', context)

    def duplicate_link(self, obj):
        return mark_safe(
            '<a href="%s?campaign=%s&duplicate=true">duplicate</a>'
            % (reverse('admin:campaign_campaign_add'), obj.id)
        )

    class Media:
        js = ('js/admin.js',)


class OrderProductInline(admin.TabularInline):
    model = OrderProduct
    formset = OrderProductInlineFormset
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin, OrderActionsMixin):
    list_display = (
        'order_id',
        'reference',
        'campaign',
        'organization',
        'order_date_time',
        'status',
        'employee_name',
        'employee_group',
        'phone_number',
        'additional_phone_number',
        'ordered_product_names',
        'ordered_product_types',
        'user_address',
        'dc_status',
    )

    list_filter = (
        'campaign_employee_id__campaign',
        'campaign_employee_id__campaign__organization',
        'status',
        'order_date_time',
        'orderproduct__product_id__product_id__product_type',
        'orderproduct__product_id__product_id__product_kind',
    )

    search_fields = (
        'reference',
        'order_id',
        'orderproduct__product_id__product_id__name_en',
        'orderproduct__product_id__product_id__name_he',
    )

    inlines = [OrderProductInline]

    actions = [
        'export_as_xlsx',
        'send_orders',
    ]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('campaign_employee_id__employee__employee_group')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if obj and obj.pk is not None:
            # for existing orders filter campaign employee choices to only ones
            # that are related to the same campaign, otherwise there will be
            # thousands of options here and the page won't even load
            form.base_fields[
                'campaign_employee_id'
            ].queryset = CampaignEmployee.objects.filter(
                campaign=obj.campaign_employee_id.campaign
            )

        return form

    def user_address(self, obj):
        return format_with_none_replacement(
            '{delivery_street} {delivery_street_number}'
            '{delivery_apartment_number}{delivery_city}'
            '{delivery_additional_details}',
            delivery_street=obj.delivery_street,
            delivery_street_number=obj.delivery_street_number,
            delivery_apartment_number=obj.delivery_apartment_number,
            delivery_city=obj.delivery_city,
            delivery_additional_details=obj.delivery_additional_details,
        )

    def employee_group(self, obj):
        return obj.campaign_employee_id.employee.employee_group

    def dc_status(self, obj):
        return obj.logistics_center_status

    def order_id(self, obj):
        # order_id is annotated by the custom model manager
        return obj.order_id

    employee_group.short_description = 'Employee Group'
    user_address.short_description = 'User Address'
    dc_status.short_description = 'DC Status'


@admin.register(OrganizationProduct)
class OrganizationProductAdmin(admin.ModelAdmin):
    list_display = (
        'organization',
        'product',
        'price',
    )
    list_filter = ('organization',)
    list_display_links = ('price',)
