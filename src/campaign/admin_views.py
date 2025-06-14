import json
from time import time
import urllib.parse

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage
from django.db.models import CharField, Count, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, Concat
from django.forms import formset_factory
from django.forms.models import model_to_dict
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils.translation import ngettext
from django.views.decorators.http import require_http_methods
from django.views.generic import View
from formtools.wizard.views import SessionWizardView
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from campaign.admin_forms import (
    AddCampaignProductsForm,
    AddQuickOfferProductsForm,
    CampaignCustomizationForm,
    CampaignForm,
    EmployeeGroupCampaignForm,
    QuickOfferCustomizationForm,
    QuickOfferForm,
)
from campaign.models import (
    Campaign,
    CampaignEmployee,
    CampaignImpersonationToken,
    CartProduct,
    Employee,
    EmployeeGroup,
    EmployeeGroupCampaign,
    EmployeeGroupCampaignProduct,
    Order,
    OrderProduct,
    Organization,
    QuickOffer,
    QuickOfferProduct,
)
from campaign.serializers import AvailableQuickOfferSerializer
from common.admin_views import BaseAutocompleteView
from inventory.models import (
    Product,
)
from logistics.models import PurchaseOrderProduct

from .tasks import send_campaign_welcome_messages


class CampaignCreationWizard(SessionWizardView):
    template_name = 'admin/campaign_form.html'

    # default_storage is the default storage backend that is set in the
    # project's settings
    file_storage = default_storage

    form_list = [
        CampaignForm,
        formset_factory(EmployeeGroupCampaignForm, extra=0, min_num=1),
        formset_factory(AddCampaignProductsForm, extra=0, min_num=1),
        formset_factory(CampaignCustomizationForm, extra=0, min_num=1),
    ]

    def get_prefix(self, request, *args, **kwargs):
        base_prefix = super().get_prefix(request, *args, **kwargs)

        # add the campaign id to the wizard prefix (which will be part of the
        # storage prefix) so that a user can edit multiple campaigns without
        # overriding each other's data in their session storage
        campaign_id = request.GET.get('campaign', 'new')
        return f'{base_prefix}_{campaign_id}'

    def dispatch(self, request, *args, **kwargs):
        # Set condition dict based on edit mode
        campaign_id = request.GET.get('campaign')

        # Define condition functions for each step
        def always_available(wizard):
            return True

        # In edit mode, all steps are available
        if campaign_id:
            # Set condition dict allowing all steps
            self.condition_dict = {
                '0': always_available,
                '1': always_available,
                '2': always_available,
                '3': always_available,
            }

        return super().dispatch(request, *args, **kwargs)

    def post(self, *args, **kwargs):
        # Check if this is a save_step API call
        # Use POST parameter instead of headers for more reliable detection
        if self.request.POST.get('save_step') == 'true':
            return self.save_step(*args, **kwargs)

        # If wizard_goto_step is set but other form data is minimal,
        # this is a navigation-only request without saving
        has_goto_step = bool(self.request.POST.get('wizard_goto_step'))
        has_minimal_data = (
            len(self.request.POST) <= 3
        )  # wizard_goto_step + csrf + wizard_current_step

        # Additional check: make sure we don't have any real form data
        has_form_data = False
        for key in self.request.POST:
            # Check if this is a form field that would contain actual data
            # from any of the steps (0-, 1-, 2-, 3- prefix)
            if key.startswith(('0-', '1-', '2-', '3-')) and key not in (
                '0-TOTAL_FORMS',
                '1-TOTAL_FORMS',
                '2-TOTAL_FORMS',
                '3-TOTAL_FORMS',
            ):
                has_form_data = True
                break

        if has_goto_step and (has_minimal_data or not has_form_data):
            return super().post(*args, **kwargs)

        # Otherwise, process step data normally and store in session
        # Process step 0 data if available
        if self.request.POST.get('0-organization'):
            form = self.get_form(step='0', data=self.request.POST)
            if form.is_valid():
                self.storage.set_step_data('0', self.process_step(form))

        # Process step 1 data if available
        if self.request.POST.get('1-0-employee_group'):
            form = self.get_form(step='1', data=self.request.POST)
            if form.is_valid():
                self.storage.set_step_data('1', self.process_step(form))

        # Process step 2 data if available
        if self.request.POST.get('2-0-campaign_data'):
            form = self.get_form(step='2', data=self.request.POST)
            if form.is_valid():
                self.storage.set_step_data('2', self.process_step(form))

        # Process step 3 data if available
        if self.request.POST.get('3-0-login_page_title'):
            form = self.get_form(step='3', data=self.request.POST)
            if form.is_valid():
                self.storage.set_step_data('3', self.process_step(form))

        return super().post(*args, **kwargs)

    def save_step(self, *args, **kwargs):
        """
        Saves just the current step data without proceeding to the next step.
        This is used for AJAX save calls from each step.
        """
        current_step = self.steps.current

        # Get the form for the current step
        form = self.get_form(
            step=current_step, data=self.request.POST, files=self.request.FILES
        )

        # Special handling for date fields on step 0
        if current_step == '0':
            # Handle date-time fields when creating a new campaign
            start_date = self.request.POST.get('start_date_time_0')
            start_time = self.request.POST.get('start_date_time_1')
            end_date = self.request.POST.get('end_date_time_0')
            end_time = self.request.POST.get('end_date_time_1')

            # Check if this is a new campaign (no campaign ID in the URL)
            is_new_campaign = not self.request.GET.get('campaign')

            # For new campaigns, make the date fields optional for the first save
            if is_new_campaign:
                # Make a mutable copy of the data
                form.data = form.data.copy()

                # Set default dates if not provided
                if not form.data.get('0-start_date_time') and (
                    not start_date or not start_time
                ):
                    # Use a default date far in the future
                    form.data['0-start_date_time'] = '2030-01-01T00:00'

                if not form.data.get('0-end_date_time') and (
                    not end_date or not end_time
                ):
                    # Use a default date far in the future
                    form.data['0-end_date_time'] = '2030-12-31T23:59'
            else:
                # If the date-time fields are provided in the split format, combine them
                if start_date and start_time:
                    form.data = form.data.copy()  # Make a mutable copy
                    form.data['0-start_date_time'] = f'{start_date}T{start_time}'

                if end_date and end_time:
                    form.data = (
                        form.data.copy()
                        if not hasattr(form.data, '_mutable')
                        else form.data
                    )
                    form.data['0-end_date_time'] = f'{end_date}T{end_time}'

        # Validate the form
        if form.is_valid():
            # Save the step data in the wizard's storage
            self.storage.set_step_data(current_step, self.process_step(form))
            self.storage.current_step = current_step

            # Special handling for step 0 (CampaignForm)
            if current_step == '0':
                campaign_id = self.request.GET.get('campaign')

                if campaign_id:
                    # Update existing campaign
                    campaign = Campaign.objects.get(id=int(campaign_id))
                    for attr, value in form.clean().items():
                        if attr == 'tags':
                            campaign.tags.set(value)
                            continue
                        setattr(campaign, attr, value)
                    campaign.save()

                    return JsonResponse(
                        {
                            'status': 'success',
                            'message': 'Campaign info saved successfully.',
                            'campaign_id': campaign.id,
                        }
                    )
                else:
                    # For new campaigns, don't save to database yet
                    # Just store data in the session and return a success response
                    # The actual campaign will be created in the done method
                    return JsonResponse(
                        {
                            'status': 'success',
                            'message': 'Campaign info stored successfully.',
                        }
                    )

            # Special handling for step 3 (CampaignCustomizationForm)
            elif current_step == '3':
                campaign_id = self.request.GET.get('campaign')
                if campaign_id:
                    campaign = Campaign.objects.get(id=int(campaign_id))
                    for form_instance in form.forms:
                        for attr, value in form_instance.clean().items():
                            setattr(campaign, attr, value)
                    campaign.save()

            # Process step 1 (employee groups) partially
            elif current_step == '1':
                campaign_id = self.request.GET.get('campaign')
                if campaign_id and form.is_valid():
                    campaign = Campaign.objects.get(id=int(campaign_id))
                    # delete the previous group employees when submit is clicked
                    # before adding the new employee groups
                    if self.request.POST.get('save_step') == 'true':
                        egc = EmployeeGroupCampaign.objects.filter(campaign=campaign)
                        egc_products = EmployeeGroupCampaignProduct.objects.filter(
                            employee_group_campaign_id__in=egc
                        )
                        egc_products = list(
                            egc_products.values(
                                'product_id__id',
                                'discount_mode',
                                'organization_discount_rate',
                                'active',
                            )
                        )
                        EmployeeGroupCampaign.objects.filter(campaign=campaign).delete()

                    for single_form in form.forms:
                        employee_group_campaign_data = single_form.clean()
                        print(employee_group_campaign_data, 'employee_group_campaign_data')
                        if not employee_group_campaign_data:
                            continue
                        company_cost_per_employee = employee_group_campaign_data[
                            'company_cost_per_employee'
                        ]
                        # Update employee_group_campaign relation
                        egc, created = EmployeeGroupCampaign.objects.update_or_create(
                            employee_group=employee_group_campaign_data[
                                'employee_group'
                            ],
                            campaign=campaign,
                            defaults={
                                'budget_per_employee': employee_group_campaign_data[
                                    'budget_per_employee'
                                ],
                                'company_cost_per_employee': company_cost_per_employee,
                                'product_selection_mode': employee_group_campaign_data[
                                    'product_selection_mode'
                                ],
                                'displayed_currency': employee_group_campaign_data[
                                    'displayed_currency'
                                ],
                                'check_out_location': employee_group_campaign_data[
                                    'check_out_location'
                                ],
                                'default_discount': employee_group_campaign_data[
                                    'default_discount'
                                ],
                            },
                        )

                        if self.request.POST.get('save_step') == 'true':
                            for egc_product in egc_products:
                                EmployeeGroupCampaignProduct.objects.create(
                                    employee_group_campaign_id=egc,
                                    product_id=Product.objects.get(
                                        id=egc_product['product_id__id']
                                    ),
                                    discount_mode=egc_product['discount_mode'],
                                    organization_discount_rate=egc_product[
                                        'organization_discount_rate'
                                    ],
                                    active=egc_product['active'],
                                )

            # Process step 2 (products)
            elif current_step == '2':
                campaign_id = self.request.GET.get('campaign')
                if campaign_id and form.is_valid():
                    campaign = Campaign.objects.get(id=int(campaign_id))

                    for idx, single_form in enumerate(form.forms):
                        # Get campaign data from the form submission
                        campaign_data_json = self.request.POST.get(
                            f'2-{idx}-campaign_data'
                        )

                        try:
                            campaign_data = (
                                json.loads(campaign_data_json)
                                if campaign_data_json
                                else {}
                            )
                        except json.JSONDecodeError:
                            campaign_data = {}

                        product_list = campaign_data.get('selected_products', [])
                        discount_modes = campaign_data.get('discount_modes', {})
                        discount_rates = campaign_data.get('discount_rates', {})
                        company_costs = campaign_data.get('company_costs', {})
                        products = Product.objects.filter(pk__in=product_list)

                        # Get the employee group campaign for this index
                        employee_group_campaigns = EmployeeGroupCampaign.objects.filter(
                            campaign=campaign
                        ).order_by('id')

                        if idx < len(employee_group_campaigns):
                            employee_group_campaign = employee_group_campaigns[idx]

                            # Process selected products
                            for product in products:
                                # Retrieve discount mode from the JSON
                                matching_mode = discount_modes.get(str(product.id))
                                if matching_mode is None:
                                    discount_mode_value = (
                                        employee_group_campaign.default_discount
                                    )
                                else:
                                    discount_mode_value = matching_mode

                                # Retrieve discount rate from the JSON
                                matching_rate = discount_rates.get(str(product.id))
                                if (
                                    matching_rate is not None
                                    and product.product_kind == 'MONEY'
                                ):
                                    try:
                                        organization_discount_rate_vl = float(
                                            matching_rate
                                        )
                                    except ValueError:
                                        organization_discount_rate_vl = None
                                else:
                                    organization_discount_rate_vl = None

                                # Retrieve individual company cost from the JSON
                                individual_company_cost = company_costs.get(
                                    str(product.id)
                                )

                                # Build defaults dict
                                defaults = {
                                    'discount_mode': discount_mode_value,
                                    'organization_discount_rate': (
                                        organization_discount_rate_vl
                                    ),
                                    'active': True,
                                }

                                # Only add company_cost_per_employee if the field exists
                                # (after migration is run)
                                if individual_company_cost is not None:
                                    try:
                                        defaults['company_cost_per_employee'] = int(
                                            individual_company_cost
                                        )
                                    except (ValueError, TypeError):
                                        pass
                                    except Exception:
                                        # Column doesn't exist yet - ignore for now
                                        pass

                                try:
                                    EmployeeGroupCampaignProduct.objects.update_or_create(
                                        employee_group_campaign_id=employee_group_campaign,
                                        product_id=product,
                                        defaults=defaults,
                                    )
                                except Exception as e:
                                    # If column doesn't exist, create
                                    # without company_cost_per_employee
                                    if 'company_cost_per_employee' in str(e):
                                        defaults_without_company_cost = {
                                            'discount_mode': discount_mode_value,
                                            'organization_discount_rate': (
                                                organization_discount_rate_vl
                                            ),
                                            'active': True,
                                        }
                                        EmployeeGroupCampaignProduct.objects.update_or_create(
                                            employee_group_campaign_id=employee_group_campaign,
                                            product_id=product,
                                            defaults=defaults_without_company_cost,
                                        )
                                    else:
                                        raise

            return JsonResponse(
                {
                    'status': 'success',
                    'message': f'Step {int(current_step) + 1} saved successfully.',
                }
            )
        else:
            # If the form is not valid, return the errors
            return JsonResponse(
                {
                    'status': 'error',
                    'message': 'Please correct the errors below.',
                    'errors': form.errors.as_json(),
                },
                status=400,
            )

    def prepare_products(self, employee_groups, step_product):
        if not employee_groups:
            return []

        try:
            campaign_data = json.loads(step_product.get('campaign_data', '{}'))
            selected_products = campaign_data.get('selected_products', [])

            result = []
            for product_id in selected_products:
                product = Product.objects.filter(id=product_id).first()
                if not product:
                    continue

                if 'employee_group_id' not in employee_groups[0]:
                    result.append(
                        {
                            'product_id': product_id,
                            'discount_mode': employee_groups[0].get(
                                'default_discount', 'ZERO'
                            ),
                            'organization_discount_rate': None,
                        }
                    )
                    continue

                try:
                    existing_products = product.employeegroupcampaignproduct_set.filter(
                        employee_group_campaign_id=employee_groups[0][
                            'employee_group_id'
                        ]
                    ).values_list(
                        'id',
                        'discount_mode',
                        'organization_discount_rate',
                        'company_cost_per_employee',
                        named=True,
                    )
                except Exception:
                    # Fallback if company_cost_per_employee column doesn't exist
                    existing_products = product.employeegroupcampaignproduct_set.filter(
                        employee_group_campaign_id=employee_groups[0][
                            'employee_group_id'
                        ]
                    ).values_list(
                        'id',
                        'discount_mode',
                        'organization_discount_rate',
                        named=True,
                    )

                if existing_products:
                    for existing in existing_products:
                        product_data = {
                            'product_id': product_id,
                            'discount_mode': existing.discount_mode,
                            'organization_discount_rate': (
                                existing.organization_discount_rate
                            ),
                        }
                        # Add company cost if it exists
                        if (
                            hasattr(existing, 'company_cost_per_employee')
                            and existing.company_cost_per_employee is not None
                        ):
                            product_data['company_cost'] = (
                                existing.company_cost_per_employee
                            )
                        result.append(product_data)
                else:
                    result.append(
                        {
                            'product_id': product_id,
                            'discount_mode': employee_groups[0].get(
                                'default_discount', 'ZERO'
                            ),
                            'organization_discount_rate': None,
                        }
                    )

            return result
        except (json.JSONDecodeError, KeyError, IndexError, AttributeError):
            return []

    def get_context_data(self, form, **kwargs):
        meta = '{}'
        campaign_id = self.request.GET.get('campaign')
        is_edit_mode = bool(campaign_id)

        if self.steps.current == '1':
            if is_edit_mode:
                campaign = Campaign.objects.get(id=int(campaign_id))
                employee_group_campaign = EmployeeGroupCampaign.objects.filter(
                    campaign=campaign
                ).first()
                if employee_group_campaign:
                    organization = employee_group_campaign.employee_group.organization
                    for nested_form in form.forms:
                        nested_form.fields[
                            'employee_group'
                        ].queryset = organization.employeegroup_set.all()

                    if campaign.campaign_type == 'WALLET':
                        for nested_form in form.forms:
                            nested_form.fields['product_selection_mode'].choices = [
                                ('MULTIPLE', 'Multiple')
                            ]
                            nested_form.fields[
                                'product_selection_mode'
                            ].initial = 'MULTIPLE'
                            nested_form.fields['product_selection_mode'].disabled = True

            first_step_data = self.get_cleaned_data_for_step('0')
            if first_step_data and 'organization' in first_step_data:
                for nested_form in form.forms:
                    nested_form.fields['employee_group'].queryset = first_step_data[
                        'organization'
                    ].employeegroup_set.all()

                    if first_step_data.get('campaign_type') == 'WALLET':
                        nested_form.fields['product_selection_mode'].choices = [
                            ('MULTIPLE', 'Multiple')
                        ]
                        nested_form.fields[
                            'product_selection_mode'
                        ].initial = 'MULTIPLE'
                        nested_form.fields['product_selection_mode'].disabled = True
        elif self.steps.current == '2':
            step_products = self.get_cleaned_data_for_step('2')
            employee_groups = self.get_cleaned_data_for_step('1')
            first_step_data = self.get_cleaned_data_for_step('0')

            init_data = {}
            organization_id = None
            campaign = None  # Initialize campaign variable

            if first_step_data and 'organization' in first_step_data:
                organization_id = first_step_data.get('organization').id
            elif is_edit_mode:
                campaign = Campaign.objects.get(id=int(campaign_id))
                employee_group_campaign = EmployeeGroupCampaign.objects.filter(
                    campaign=campaign
                ).first()
                if employee_group_campaign:
                    organization_id = (
                        employee_group_campaign.employee_group.organization.id
                    )

            if organization_id:
                init_data['organization_id'] = organization_id
                products = []

                if employee_groups:
                    employee_groups = [
                        {
                            'employee_group_id': employee_group.get(
                                'employee_group'
                            ).id,
                            'name': employee_group.get('employee_group').name,
                            'budget': employee_group.get('budget_per_employee'),
                            'company_cost': employee_group.get(
                                'company_cost_per_employee'
                            ),
                            'default_discount': employee_group.get('default_discount'),
                        }
                        for employee_group in employee_groups
                    ]
                elif is_edit_mode:
                    employee_groups = [
                        {
                            'employee_group_id': eg.employee_group.id,
                            'name': eg.employee_group.name,
                            'budget': eg.budget_per_employee,
                            'company_cost': eg.company_cost_per_employee,
                            'default_discount': eg.default_discount,
                        }
                        for eg in EmployeeGroupCampaign.objects.filter(
                            campaign_id=campaign_id
                        ).select_related('employee_group')
                    ]

                if employee_groups:
                    init_data.update({'employee_groups': employee_groups})

                total_group_products = 0
                if len(form.initial) > 0 and not step_products:
                    total_group_products = len(form.initial)
                    init_data.update(
                        {
                            'products': [
                                [
                                    {
                                        'product_id': el['product_id'],
                                        'discount_mode': el['discount_mode'],
                                        'organization_discount_rate': el[
                                            'organization_discount_rate'
                                        ],
                                        'company_cost': el.get('company_cost'),
                                    }
                                    for el in element.get('products')
                                ]
                                for element in form.initial
                            ]
                        }
                    )
                # we need to send the total initial
                init_data.update({'total_group_products': total_group_products})

                if step_products:
                    for step_product in step_products:
                        if step_product.get('campaign_data'):
                            products.append(
                                self.prepare_products(
                                    employee_groups=employee_groups,
                                    step_product=step_product,
                                )
                            )
                            continue
                        products.append([])
                    init_data.update({'products': products})

                if campaign_id:
                    init_data.update({'campaign_id': campaign_id})
                    # Ensure campaign is defined before accessing its status
                    if campaign is None:
                        campaign = Campaign.objects.get(id=int(campaign_id))
                    init_data.update({'campaign_status': campaign.status})

                init_data.update(
                    {
                        'type': 'campaign',
                    }
                )
                quick_offers = QuickOffer.objects.annotate(
                    product_count=Count('selected_products')
                ).filter(product_count__gt=0)
                init_data.update(
                    {
                        'quick_offers': AvailableQuickOfferSerializer(
                            quick_offers, many=True
                        ).data,
                    }
                )
                meta = json.dumps(init_data)
        context = super().get_context_data(form=form, **kwargs)
        context['meta'] = meta
        return context

    def get_form_initial(self, step):
        campaign_id = self.request.GET.get('campaign')
        duplicate = self.request.GET.get('duplicate') in ('1', 'true', 'yes')

        if campaign_id:
            campaign = Campaign.objects.get(id=int(campaign_id))
            employee_group_campaign = EmployeeGroupCampaign.objects.filter(
                campaign=campaign
            ).first()
            organization = employee_group_campaign.employee_group.organization
            if step == '0':
                initial = {'organization': organization.pk} | model_to_dict(campaign)

                # a duplicated campaign would usually be created for a
                # different organization
                if duplicate:
                    initial.pop('organization', None)

                return initial
            elif step == '1':
                if campaign_id and not duplicate:
                    employee_group_campaigns = EmployeeGroupCampaign.objects.filter(
                        campaign=campaign
                    ).values(
                        'employee_group',
                        'budget_per_employee',
                        'company_cost_per_employee',
                        'product_selection_mode',
                        'displayed_currency',
                        'check_out_location',
                        'default_discount',
                    )
                    return employee_group_campaigns

                # only use existing employee groups as initial data if we are
                # not duplicating
                if not duplicate:
                    step_0_data = self.get_cleaned_data_for_step('0')
                    if step_0_data and step_0_data.get('organization') == organization:
                        employee_group_campaigns = EmployeeGroupCampaign.objects.filter(
                            campaign=campaign
                        ).values(
                            'employee_group',
                            'budget_per_employee',
                            'company_cost_per_employee',
                            'product_selection_mode',
                            'displayed_currency',
                            'check_out_location',
                            'default_discount',
                        )
                        return employee_group_campaigns
            elif step == '2':
                EGCP = EmployeeGroupCampaignProduct
                if campaign_id and not duplicate:
                    try:
                        selected_products = [
                            {
                                'products': [
                                    {
                                        'product_id': egcp[
                                            'product_id'
                                        ],  # Accessing as dictionary key
                                        'discount_mode': egcp['discount_mode'],
                                        'organization_discount_rate': egcp[
                                            'organization_discount_rate'
                                        ],
                                        'company_cost': egcp.get(
                                            'company_cost_per_employee'
                                        ),
                                    }
                                    for egcp in EGCP.objects.filter(
                                        employee_group_campaign_id=el, active=True
                                    ).values(
                                        'product_id',
                                        'discount_mode',
                                        'organization_discount_rate',
                                        'company_cost_per_employee',
                                    )
                                ]
                            }
                            for el in EmployeeGroupCampaign.objects.filter(
                                campaign=campaign
                            )
                        ]
                    except Exception:
                        # Fallback if company_cost_per_employee column doesn't exist
                        selected_products = [
                            {
                                'products': [
                                    {
                                        'product_id': egcp[
                                            'product_id'
                                        ],  # Accessing as dictionary key
                                        'discount_mode': egcp['discount_mode'],
                                        'organization_discount_rate': egcp[
                                            'organization_discount_rate'
                                        ],
                                    }
                                    for egcp in EGCP.objects.filter(
                                        employee_group_campaign_id=el, active=True
                                    ).values(
                                        'product_id',
                                        'discount_mode',
                                        'organization_discount_rate',
                                    )
                                ]
                            }
                            for el in EmployeeGroupCampaign.objects.filter(
                                campaign=campaign
                            )
                        ]
                    return selected_products

                try:
                    selected_products = [
                        {
                            'products': [
                                {
                                    'product_id': egcp[
                                        'product_id'
                                    ],  # Accessing as dictionary key
                                    'discount_mode': egcp['discount_mode'],
                                    'organization_discount_rate': egcp[
                                        'organization_discount_rate'
                                    ],
                                    'company_cost': egcp.get(
                                        'company_cost_per_employee'
                                    ),
                                }
                                for egcp in EmployeeGroupCampaignProduct.objects.filter(
                                    employee_group_campaign_id=el, active=True
                                ).values(
                                    'product_id',
                                    'discount_mode',
                                    'organization_discount_rate',
                                    'company_cost_per_employee',
                                )
                            ]
                        }
                        for el in EmployeeGroupCampaign.objects.filter(
                            campaign=campaign
                        )
                    ]
                except Exception:
                    # Fallback if company_cost_per_employee column doesn't exist
                    selected_products = [
                        {
                            'products': [
                                {
                                    'product_id': egcp[
                                        'product_id'
                                    ],  # Accessing as dictionary key
                                    'discount_mode': egcp['discount_mode'],
                                    'organization_discount_rate': egcp[
                                        'organization_discount_rate'
                                    ],
                                }
                                for egcp in EmployeeGroupCampaignProduct.objects.filter(
                                    employee_group_campaign_id=el, active=True
                                ).values(
                                    'product_id',
                                    'discount_mode',
                                    'organization_discount_rate',
                                )
                            ]
                        }
                        for el in EmployeeGroupCampaign.objects.filter(
                            campaign=campaign
                        )
                    ]

                # manipulate the original campaign's list of selected campaign
                # products so that it is the same length as the list of newly
                # selected employee groups for the duplicated campaign
                if duplicate:
                    all_selected_products = [
                        {
                            'product_id': p['product_id'],
                            'discount_mode': p['discount_mode'],
                            'organization_discount_rate': p[
                                'organization_discount_rate'
                            ],
                            'company_cost': p.get('company_cost'),
                        }
                        for sp in selected_products
                        for p in sp['products']
                    ]
                    step_1_employee_groups = self.get_cleaned_data_for_step('1')
                    if step_1_employee_groups:
                        return [{'products': all_selected_products}] * len(
                            step_1_employee_groups
                        )
                    return [{'products': all_selected_products}]
                return selected_products
            elif step == '3':
                initial = [model_to_dict(campaign)]
                return initial

        return self.initial_dict.get(step, {})

    def done(self, form_list, **kwargs):
        """
        Final submission logic after all wizard steps are completed.
        For new campaigns, this is where all data is actually saved to the database.
        For existing campaigns, this updates any changed data.
        """
        campaign_id = self.request.GET.get('campaign')
        duplicate = self.request.GET.get('duplicate') in ('1', 'true', 'yes')
        change_message = []

        if form_list[0].is_valid():
            # on duplication we should ignore the existing campaign
            if campaign_id and not duplicate:
                # if we are editing an existing campaign fetch it and modify
                campaign = Campaign.objects.get(id=int(campaign_id))
                for attr, value in form_list[0].clean().items():
                    if attr == 'tags':
                        campaign.tags.set(value)
                        continue
                    setattr(campaign, attr, value)
            else:
                # if we are creating a campaign we can just save this form
                campaign = form_list[0].save()

        if form_list[1].is_valid():
            selected_campaign_employee_groups = []

            for idx, single_form in enumerate(form_list[1].forms):
                # Instead of individual product fields, get the consolidated
                # JSON from step 2.
                campaign_data_json = self.storage.get_step_data('2').get(
                    f'2-{idx}-campaign_data'
                )
                try:
                    campaign_data = (
                        json.loads(campaign_data_json) if campaign_data_json else {}
                    )
                except json.JSONDecodeError:
                    campaign_data = {}
                # Extract the selected product IDs, discount modes, and discount rates.
                product_list = campaign_data.get('selected_products', [])
                discount_modes = campaign_data.get('discount_modes', {})
                discount_rates = campaign_data.get('discount_rates', {})
                company_costs = campaign_data.get('company_costs', {})
                products = Product.objects.filter(pk__in=product_list)
                employee_group_campaign_data = single_form.clean()
                if not employee_group_campaign_data:
                    continue
                # Update campaign employees' budget.
                for employee in employee_group_campaign_data[
                    'employee_group'
                ].employee_set.all():
                    CampaignEmployee.objects.get_or_create(
                        campaign=campaign,
                        employee=employee,
                        defaults={
                            'total_budget': employee_group_campaign_data[
                                'budget_per_employee'
                            ]
                        },
                    )

                employee_group_campaign, created = (
                    EmployeeGroupCampaign.objects.update_or_create(
                        employee_group=employee_group_campaign_data['employee_group'],
                        campaign=campaign,
                        defaults={
                            'budget_per_employee': employee_group_campaign_data[
                                'budget_per_employee'
                            ],
                            'company_cost_per_employee': employee_group_campaign_data[
                                'company_cost_per_employee'
                            ],
                            'product_selection_mode': employee_group_campaign_data[
                                'product_selection_mode'
                            ],
                            'displayed_currency': employee_group_campaign_data[
                                'displayed_currency'
                            ],
                            'check_out_location': employee_group_campaign_data[
                                'check_out_location'
                            ],
                            'default_discount': employee_group_campaign_data[
                                'default_discount'
                            ],
                        },
                    )
                )

                if created:
                    change_message.append(
                        'Employee group added: '
                        f'{employee_group_campaign_data["employee_group"].name}'
                    )

                # keep a list of employee groups set in this campaign so we can
                # delete others if any exist (this facilitates editing of an
                # existing campaign and changing one of the selected employee
                # groups
                selected_campaign_employee_groups.append(
                    employee_group_campaign_data['employee_group']
                )
                employee_group = employee_group_campaign_data.get('employee_group')
                employee_group.campaigns.add(campaign)

                added_products = []
                removed_products = []

                # Process each selected product.
                for product in products:
                    # Retrieve discount mode from the JSON. keys are strings because
                    # of js limits
                    matching_mode = discount_modes.get(str(product.id))
                    if matching_mode is None:
                        discount_mode_value = employee_group_campaign_data[
                            'default_discount'
                        ]
                    else:
                        discount_mode_value = matching_mode

                    # Retrieve discount rate from the JSON.
                    matching_rate = discount_rates.get(str(product.id))
                    if matching_rate is not None and product.product_kind == 'MONEY':
                        try:
                            organization_discount_rate_vl = float(matching_rate)
                        except ValueError:
                            organization_discount_rate_vl = None
                    else:
                        organization_discount_rate_vl = None

                    # Retrieve individual company cost from the JSON
                    individual_company_cost = company_costs.get(str(product.id))

                    # Build defaults dict
                    defaults = {
                        'discount_mode': discount_mode_value,
                        'organization_discount_rate': organization_discount_rate_vl,
                        'active': True,
                    }

                    # Only add company_cost_per_employee if the field exists
                    # (after migration is run)
                    if individual_company_cost is not None:
                        try:
                            defaults['company_cost_per_employee'] = int(
                                individual_company_cost
                            )
                        except (ValueError, TypeError):
                            pass
                        except Exception:
                            # Column doesn't exist yet - ignore for now
                            pass

                    employee_group_campaign_product, created = (
                        EmployeeGroupCampaignProduct.objects.update_or_create(
                            employee_group_campaign_id=employee_group_campaign,
                            product_id=product,
                            defaults=defaults,
                        )
                    )

                    if created:
                        added_products.append(
                            f'{employee_group_campaign_product.id} '
                            f'({employee_group_campaign_product.product_id_id})'
                        )

                # Handle unselected products
                unselected_products = EmployeeGroupCampaignProduct.objects.filter(
                    employee_group_campaign_id=employee_group_campaign,
                ).exclude(product_id__in=products)
                for p in unselected_products.all():
                    removed_products.append(f'{p.id} ({p.product_id_id})')

                if added_products:
                    change_message.append(
                        f'{employee_group_campaign_data["employee_group"].name} '
                        f'added products: {", ".join(added_products)}'
                    )
                if removed_products:
                    change_message.append(
                        f'{employee_group_campaign_data["employee_group"].name} '
                        f'removed products: {", ".join(removed_products)}'
                    )

                # Delete associated cart products for unselected products
                CartProduct.objects.filter(product_id__in=unselected_products).delete()

                # Identify unselected products with orders
                unselected_ordered_products = unselected_products.filter(
                    id__in=OrderProduct.objects.filter(
                        product_id__in=unselected_products
                    ).values_list('product_id__id', flat=True)
                )

                # Mark ordered products as inactive
                unselected_ordered_products.update(active=False)

                # Delete unordered products
                unselected_unordered_products = unselected_products.exclude(
                    id__in=unselected_ordered_products.values_list('id', flat=True)
                )
                unselected_unordered_products.delete()

            # Delete campaign employee groups not in the current selection
            unselected_employee_group_campaigns = EmployeeGroupCampaign.objects.filter(
                campaign=campaign
            ).exclude(employee_group__in=selected_campaign_employee_groups)

            for egc in unselected_employee_group_campaigns.all():
                change_message.append(
                    f'Employee group removed: {egc.employee_group.name} (with '
                    f'{len(egc.employeegroupcampaignproduct_set.all())} '
                    'products)'
                )

            unselected_employee_group_campaigns.delete()

        if form_list[3].is_valid():
            for form in form_list[3].forms:
                for attr, value in form.clean().items():
                    setattr(campaign, attr, value)
            campaign.save()

        LogEntry.objects.log_action(
            user_id=self.request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                campaign, for_concrete_model=False
            ).id,
            object_id=campaign.pk,
            object_repr=str(campaign),
            action_flag=CHANGE if campaign_id else ADDITION,
            change_message='\n'.join(change_message),
        )

        return redirect('admin:campaign_campaign_changelist')


class CampaignImpersonateView(APIView):
    authentication_classes = [SessionAuthentication]

    def get(
        self,
        request,
        campaign_id,
        employee_group_campaign_id=None,
        campaign_employee_id=None,
    ):
        campaign = Campaign.objects.get(id=campaign_id)
        show_link = request.GET.get('showLink') == '1'

        # if this is an admin preview request we will get an employee group
        # campaign id
        if employee_group_campaign_id:
            employee_group_campaign = EmployeeGroupCampaign.objects.get(
                pk=employee_group_campaign_id
            )
        else:
            employee_group_campaign = None

        # or if this is a user impersonation request we will get a campaign
        # employee id
        if campaign_employee_id:
            campaign_employee = CampaignEmployee.objects.get(pk=campaign_employee_id)
        else:
            campaign_employee = None

        impersonation_token = CampaignImpersonationToken.objects.create(
            campaign=campaign,
            employee_group_campaign=employee_group_campaign,
            campaign_employee=campaign_employee,
            user=request.user,
            valid_until_epoch_seconds=int(time()) + 60 * 60 * 12,
        )

        # the employee site is in charge of exchanging the token for a normal
        # jwt token
        employee_site_url = (
            f'{settings.EMPLOYEE_SITE_BASE_URL}/{campaign.code}/i?t='
            f'{urllib.parse.quote_plus(impersonation_token.token)}'
        )
        if show_link:
            # show the link so that it can be copied and used elsewhere
            return HttpResponse(
                f'<html><body><a href="{employee_site_url}">{employee_site_url}'
                '</a></body></html>'
            )
        else:
            # redirect to the employee site
            return redirect(employee_site_url)


class CampaignInvitationView(LoginRequiredMixin, View):
    # TODO: Need to introduce a StaffRequiredMixin
    # or SuperuserRequiredMixin and use that instead.

    def post(self, request, campaign_id):
        """
        Handles the POST request to send campaign welcome messages
        to selected employees.

        This method processes the selected employees from the POST data,
        verifies the campaign status, and sends welcome messages
        via email or SMS to the employees. It also provides appropriate
        success or error messages based on the outcome of the operation.
        """
        try:
            selected_employees_json = request.POST.get('selected_employees', '[]')
            selected_employees = json.loads(selected_employees_json)

            campaign = Campaign.objects.get(id=campaign_id)

            if (
                campaign.get_status_display()
                != Campaign.CampaignStatusEnum.ACTIVE.value
            ):
                raise ValueError(ngettext("Campaign's status is not active"))

            # TODO: Also need to place a BE check to ensure these
            # employees haven't orderd the gift yet, since the check
            # is already on FE + its not critical so will do it later.
            campaign_employees = CampaignEmployee.objects.filter(
                id__in=selected_employees
            )
            employee_ids = [
                campaign_employee.employee.id
                for campaign_employee in campaign_employees
            ]

            send_campaign_welcome_messages.apply_async((campaign.id, employee_ids))

            employee_count = len(employee_ids)
            success_message = (
                ngettext(
                    'Successfully sent welcome message to %d employee.',
                    'Successfully sent welcome messages to %d employees.',
                    employee_count,
                )
                % employee_count
            )

            messages.success(request, success_message)

        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')

        return redirect('admin:campaign_campaign_changelist')


class CampaignEmployeeAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return CampaignEmployee.objects.none()

        qs = CampaignEmployee.objects.all()

        if self.q:
            qs = (
                qs.exclude(
                    order__status__in=[
                        Order.OrderStatusEnum.PENDING.name,
                        Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
                    ]
                )
                .annotate(
                    full_name_en=Concat(
                        F('employee__first_name_en'),
                        Value(' '),
                        F('employee__last_name_en'),
                        output_field=CharField(),
                    ),
                    full_name_he=Concat(
                        F('employee__first_name_he'),
                        Value(' '),
                        F('employee__last_name_he'),
                        output_field=CharField(),
                    ),
                )
                .filter(
                    Q(full_name_en__icontains=self.q)
                    | Q(full_name_he__icontains=self.q)
                    | Q(campaign__name_en__icontains=self.q)
                    | Q(campaign__name_he__icontains=self.q)
                    | Q(campaign__organization__name_en__icontains=self.q)
                    | Q(campaign__organization__name_he__icontains=self.q)
                )
            )

        return qs

    def get_result_label(self, result):
        return (
            f'{result.employee.full_name} | {result.campaign.name} | '
            f'{result.campaign.organization.name}'
        )


class QuickOfferCreationWizard(SessionWizardView):
    template_name = 'admin/quick_offer_form.html'
    file_storage = default_storage
    form_list = [
        QuickOfferForm,
        formset_factory(AddQuickOfferProductsForm, extra=0, min_num=1),
        formset_factory(QuickOfferCustomizationForm, extra=0, min_num=1),
    ]

    def post(self, *args, **kwargs):
        if self.request.POST.get('1-0-products'):
            form = self.get_form(step='1', data=self.request.POST)
            if form.is_valid():
                self.storage.set_step_data('1', self.process_step(form))
        return super().post(*args, **kwargs)

    def get_form_initial(self, step):
        quick_offer_id = self.request.GET.get('quick_offer_id')
        duplicate = self.request.GET.get('duplicate') in ('1', 'true', 'yes')
        if quick_offer_id:
            quick_offer = QuickOffer.objects.get(id=int(quick_offer_id))
            if step == '0':
                initial = model_to_dict(quick_offer)
                if duplicate:
                    initial.pop('organization', None)
                return initial
            elif step == '2':
                return [model_to_dict(quick_offer)]
        if step == '2':
            return [
                {
                    'login_page_title': 'Gifts for employees',
                    'login_page_title_he': 'מתנות לעובדים',
                    'login_page_subtitle': 'Welcome!',
                    'login_page_subtitle_he': 'ברוכים הבאים!',
                    'main_page_first_banner_title': 'All gifts in one place',
                    'main_page_first_banner_title_he': 'כל המתנות במקום אחד',
                    'main_page_first_banner_subtitle': 'On this site you can choose '
                    'gifts for branding from a wide variety of categories '
                    'and products in varying budgets.',
                    'main_page_first_banner_subtitle_he': 'באתר זה תוכלו לבחור'
                    ' מתנות למיתוג ממגוון רחב של קטגוריות ומוצרים בתקציבים משתנים.',
                    'main_page_second_banner_title': 'A little more information',
                    'main_page_second_banner_title_he': 'עוד קצת מידע',
                    'main_page_second_banner_subtitle': 'A little more information '
                    'Prices do not include branding unless'
                    'otherwise stated on the product page.\n'
                    'Delivery times: between 5 and 10 business days\n'
                    'Delivery times during the holidays: 14 business days\n'
                    'The indicated price is per 100 units. '
                    'In smaller quantities there may be a change in price.\n'
                    'You can get discounts on some products '
                    'with the customer manager.\n'
                    '*Prices do not include branding, shipping and packaging\n'
                    'Have a fun choice!\n',
                    'main_page_second_banner_subtitle_he': 'המחירים אינם כוללים מיתוג'
                    ' אלא אם צוין אחרת בעמוד המוצר.\n'
                    'זמני אספקה: בין 5 ל10 ימי עסקים\n'
                    'זמני אספקה בתקופות החגים: 14 ימי עסקים\n'
                    'המחיר המצויין הינו לפי 100 יחידות.'
                    ' בכמויות קטנות יותר עלול להיות שינוי במחיר.\n'
                    'ניתן לקבל הנחות על חלק מהמוצרים מול מנהל הלקוח.\n'
                    '*מחירים אינם כוללים מיתוג, שילוח ואריזה\n'
                    'שתהיה בחירה מהנה!\n',
                    'main_page_second_banner_text_color': 'WHITE',
                    'sms_sender_name': '',
                    'sms_welcome_text': '',
                    'sms_welcome_text_he': '',
                    'email_welcome_text': '',
                    'email_welcome_text_he': '',
                }
            ]
        return self.initial_dict.get(step, {})

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        quick_offer_id = self.request.GET.get('quick_offer_id')
        if self.steps.current == '1':
            organization_id = self.get_cleaned_data_for_step('0').get('organization').id
            meta = {
                'organization_id': organization_id,
                'employee_groups': [{'name': '', 'budget': ''}],
                'type': 'quick_offer',
            }
            if quick_offer_id:
                quick_offer = QuickOffer.objects.get(id=int(quick_offer_id))
                meta['products'] = {
                    '0': list(
                        quick_offer.products.all()
                        .annotate(
                            product_id=F('id'),
                            organization_discount_rate=Coalesce(
                                Subquery(
                                    QuickOfferProduct.objects.filter(
                                        product=OuterRef('id'),
                                        quick_offer=Value(quick_offer.id),
                                    ).values('organization_discount_rate'),
                                ),
                                F('client_discount_rate'),
                                output_field=CharField(),
                            ),
                        )
                        .values(
                            'product_id',
                            'organization_discount_rate',
                        )
                    )
                }
            context['meta'] = json.dumps(meta)
        return context

    def done(self, form_list, **kwargs):
        quick_offer_id = self.request.GET.get('quick_offer_id')
        duplicate = self.request.GET.get('duplicate') in ('1', 'true', 'yes')
        if quick_offer_id and not duplicate:
            quick_offer = QuickOffer.objects.get(id=int(quick_offer_id))
            quick_offer.tags.clear()
            if form_list[0].is_valid():
                for attr, value in form_list[0].clean().items():
                    if attr != 'tags':
                        setattr(quick_offer, attr, value)
            tags = self.get_cleaned_data_for_step('0').get('tags')
            for tag in tags:
                quick_offer.tags.add(tag)
        else:
            quick_offer = form_list[0].save()

        product_data = self.storage.get_step_data('1').get('1-0-products')
        if product_data:
            try:
                product_data = json.loads(
                    product_data
                )  # Convert to a Python dictionary
                product_list = product_data.get(
                    'selected_products', []
                )  # Extract product IDs
            except json.JSONDecodeError:
                product_list = []  # Fallback in case of JSON parsing error
        else:
            product_list = []
        products = Product.objects.filter(pk__in=product_list)

        if form_list[2].is_valid():
            for form in form_list[2].forms:
                for attr, value in form.clean().items():
                    setattr(quick_offer, attr, value)

        # save the organization rates
        organization_discount_rates = product_data.get('discount_rates')

        # remove the removed products
        QuickOfferProduct.objects.filter(quick_offer=quick_offer).exclude(
            product__in=products
        ).delete()

        for product in products:
            if str(product.id) in organization_discount_rates:
                organization_discount_rate_vl = float(
                    organization_discount_rates[str(product.id)]
                )
            else:
                organization_discount_rate_vl = None

            obj, _ = QuickOfferProduct.objects.get_or_create(
                quick_offer=quick_offer, product=product
            )
            obj.organization_discount_rate = organization_discount_rate_vl
            obj.save()

        quick_offer.save()

        return redirect('admin:campaign_quickoffer_changelist')


class QuickOfferImpersonateView(APIView):
    authentication_classes = [SessionAuthentication]

    def get(self, request, quick_offer_id):
        quick_offer = QuickOffer.objects.get(id=quick_offer_id)
        show_link = request.GET.get('showLink') == '1'
        CampaignImpersonationToken.objects.all().delete()
        impersonation_token = CampaignImpersonationToken.objects.create(
            quick_offer=quick_offer,
            user=request.user,
            valid_until_epoch_seconds=int(time()) + 60 * 60 * 12,
        )

        employee_site_url = (
            f'{settings.EMPLOYEE_SITE_BASE_URL}/{quick_offer.code}/i?t='
            f'{urllib.parse.quote_plus(impersonation_token.token)}'
        )
        if show_link:
            # show the link so that it can be copied and used elsewhere
            return HttpResponse(
                f'<html><body><a href="{employee_site_url}">{employee_site_url}'
                '</a></body></html>'
            )
        else:
            # redirect to the employee site
            return redirect(employee_site_url)


@staff_member_required
@require_http_methods(['POST'])
def update_employee_budget(request, employee_id):
    try:
        data = json.loads(request.body)
        new_budget = data.get('total_budget')
        campaign_code = data.get('campaign_code')
        employee = Employee.objects.get(id=employee_id)
        campaign = Campaign.objects.filter(code=campaign_code).first()
        CampaignEmployee.objects.filter(employee=employee, campaign=campaign).update(
            total_budget=new_budget
        )
        # Calculate new left budget
        left_budget = float(new_budget) - float(
            employee.used_budget_campaign(campaign) or 0
        )

        return JsonResponse(
            {'status': 'success', 'left_budget': left_budget if left_budget > 0 else 0}
        )
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


class PurchaseOrderProductAutocomplete(AutocompleteJsonView):
    model = PurchaseOrderProduct
    search_fields = ['purchase_order__id', 'product_id__name']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.q:
            qs = qs.filter(
                Q(purchase_order__id__icontains=self.q)
                | Q(product_id__name__icontains=self.q)
            )
        return qs

    def get_result_label(self, obj):
        return f'PO #{obj.purchase_order.id} - {obj.product_id.name}'

    def get_result_value(self, obj):
        # The value that will be stored in the form
        return obj.id


class OrganizationAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return Organization.objects.none()

        qs = Organization.objects.all()

        if self.q:
            qs = qs.filter(name_he__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.name_he


class EmployeeGroupCampaignProductAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return EmployeeGroupCampaignProduct.objects.none()

        qs = EmployeeGroupCampaignProduct.objects.all()

        if self.q:
            qs = qs.filter(product_id__product_id__name_he__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.product_id.name_he


class EmployeeGroupAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return EmployeeGroup.objects.none()

        qs = EmployeeGroup.objects.all()

        if self.q:
            qs = qs.filter(name__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.name


class QuickOfferAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return QuickOffer.objects.none()

        qs = QuickOffer.objects.annotate(
            product_count=Count('selected_products')
        ).filter(product_count__gt=0)

        if self.q:
            qs = qs.filter(name__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.name
