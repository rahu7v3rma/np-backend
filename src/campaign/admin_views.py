import json
from time import time
import urllib.parse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.forms import formset_factory
from django.forms.models import model_to_dict
from django.shortcuts import redirect
from django.utils.translation import ngettext
from django.views.generic import View
from formtools.wizard.views import SessionWizardView
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from campaign.admin_forms import (
    AddCampaignProductsForm,
    CampaignCustomizationForm,
    CampaignForm,
    EmployeeGroupCampaignForm,
)
from campaign.models import (
    Campaign,
    CampaignEmployee,
    CampaignImpersonationToken,
    EmployeeGroupCampaign,
    EmployeeGroupCampaignProduct,
)
from inventory.models import (
    Product,
)

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

    def post(self, *args, **kwargs):
        if self.request.POST.get('1-0-employee_group'):
            form = self.get_form(step='1', data=self.request.POST)
            if form.is_valid():
                self.storage.set_step_data('1', self.process_step(form))

        if self.request.POST.get('2-0-products'):
            form = self.get_form(step='2', data=self.request.POST)
            if form.is_valid():
                self.storage.set_step_data('2', self.process_step(form))

        if self.request.POST.get('3-0-login_page_title'):
            form = self.get_form(step='3', data=self.request.POST)
            if form.is_valid():
                self.storage.set_step_data('3', self.process_step(form))

        return super().post(*args, **kwargs)

    def get_context_data(self, form, **kwargs):
        meta = '{}'
        if self.steps.current == '1':
            first_step_data = self.get_cleaned_data_for_step('0')
            for nested_form in form.forms:
                nested_form.fields['employee_group'].queryset = first_step_data[
                    'organization'
                ].employeegroup_set.all()
        elif self.steps.current == '2':
            step_products = self.get_cleaned_data_for_step('2')
            employee_groups = self.get_cleaned_data_for_step('1')
            organization_id = self.get_cleaned_data_for_step('0').get('organization').id
            init_data = {}
            init_data['organization_id'] = organization_id
            products = []
            if employee_groups:
                employee_groups = [
                    {
                        'name': employee_group.get('employee_group').name,
                        'budget': employee_group.get('budget_per_employee'),
                    }
                    for employee_group in employee_groups
                ]
                init_data.update({'employee_groups': employee_groups})

            if len(form.initial) > 0:
                init_data.update(
                    {
                        'products': [
                            [el.id for el in element.get('products')]
                            for element in form.initial
                        ]
                    }
                )
            if step_products:
                for step_product in step_products:
                    if step_product.get('products'):
                        products.append(
                            [
                                product_ids[0]
                                for product_ids in step_product.get(
                                    'products'
                                ).values_list('id')
                            ]
                        )
                        continue
                    products.append([])
                init_data.update({'products': products})
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
                # only use existing employee groups as initial data if we are
                # not duplicating
                if not duplicate:
                    selected_organization = self.get_cleaned_data_for_step('0').get(
                        'organization'
                    )
                    if selected_organization == organization:
                        employee_group_campaigns = EmployeeGroupCampaign.objects.filter(
                            campaign=campaign
                        ).values(
                            'employee_group',
                            'budget_per_employee',
                            'product_selection_mode',
                            'displayed_currency',
                        )
                        return employee_group_campaigns
            elif step == '2':
                selected_products = [
                    {
                        'products': [
                            egcp.product_id
                            for egcp in EmployeeGroupCampaignProduct.objects.filter(
                                employee_group_campaign_id=el
                            ).all()
                        ]
                    }
                    for el in EmployeeGroupCampaign.objects.filter(campaign=campaign)
                ]

                # manipulate the original campaign's list of selected campaign
                # products so that it is the same length as the list of newly
                # selected employee groups for the duplicated campaign
                if duplicate:
                    step_1_employee_groups = self.get_cleaned_data_for_step('1')
                    while len(step_1_employee_groups) < len(selected_products):
                        selected_products.pop()
                    while len(step_1_employee_groups) > len(selected_products):
                        selected_products.append({'products': []})

                return selected_products
            elif step == '3':
                initial = [model_to_dict(campaign)]
                return initial

        return self.initial_dict.get(step, {})

    def done(self, form_list, **kwargs):
        campaign_id = self.request.GET.get('campaign')
        duplicate = self.request.GET.get('duplicate') in ('1', 'true', 'yes')

        if form_list[0].is_valid():
            # on duplication we should ignore the existing campaign
            if campaign_id and not duplicate:
                # if we are editing an existing campaign fetch it and modify
                campaign = Campaign.objects.get(id=int(campaign_id))
                for attr, value in form_list[0].clean().items():
                    setattr(campaign, attr, value)
            else:
                # if we are creating a campaign we can just save this form
                campaign = form_list[0].save()
        if form_list[1].is_valid():
            selected_campaign_employee_groups = []

            for idx, single_form in enumerate(form_list[1].forms):
                product_list = self.storage.get_step_data('2').getlist(
                    f'2-{idx}-products'
                )
                products = Product.objects.filter(pk__in=product_list)

                employee_group_campaign_data = single_form.clean()
                if not employee_group_campaign_data:
                    continue

                employee_group_campaign, _created = (
                    EmployeeGroupCampaign.objects.update_or_create(
                        employee_group=employee_group_campaign_data['employee_group'],
                        campaign=campaign,
                        defaults={
                            'budget_per_employee': employee_group_campaign_data[
                                'budget_per_employee'
                            ],
                            'product_selection_mode': employee_group_campaign_data[
                                'product_selection_mode'
                            ],
                            'displayed_currency': employee_group_campaign_data[
                                'displayed_currency'
                            ],
                        },
                    )
                )

                # keep a list of employee groups set in this campaign so we can
                # delete others if any exist (this facilitates editing of an
                # existing campaign and changing one of the selected employee
                # groups
                selected_campaign_employee_groups.append(
                    employee_group_campaign_data['employee_group']
                )

                # add campaign to employee group
                employee_group = employee_group_campaign_data.get('employee_group')
                employee_group.campaigns.add(campaign)

                # add data to EmployeeGroupCampaignProduct
                for product in products:
                    EmployeeGroupCampaignProduct.objects.get_or_create(
                        employee_group_campaign_id=employee_group_campaign,
                        product_id=product,
                    )

                # delete products that were unselected
                EmployeeGroupCampaignProduct.objects.filter(
                    employee_group_campaign_id=employee_group_campaign,
                ).exclude(product_id__in=products).delete()

            # delete campaign employee groups other than the selected ones
            EmployeeGroupCampaign.objects.filter(campaign=campaign).exclude(
                employee_group__in=selected_campaign_employee_groups
            ).delete()
        if form_list[3].is_valid():
            for form in form_list[3].forms:
                for attr, value in form.clean().items():
                    setattr(campaign, attr, value)

            campaign.save()

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
            valid_until_epoch_seconds=int(time()) + 30,
        )

        # redirect to the employee site which is in charge of exchanging the
        # token for a normal jwt
        return redirect(
            f'{settings.EMPLOYEE_SITE_BASE_URL}/{campaign.code}/i?t='
            f'{urllib.parse.quote_plus(impersonation_token.token)}'
        )


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
