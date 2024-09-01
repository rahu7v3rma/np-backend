from django import forms
from django.contrib.admin import site as admin_site
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.forms.models import BaseInlineFormSet

from campaign.models import (
    Campaign,
    Employee,
    EmployeeGroup,
    EmployeeGroupCampaign,
    EmployeeGroupCampaignProduct,
    Organization,
)
from inventory.models import Product


class CampaignForm(forms.ModelForm):
    organization = forms.ModelChoiceField(queryset=Organization.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        employeeGroup = EmployeeGroup()
        self.fields['organization'].widget = RelatedFieldWidgetWrapper(
            self.fields['organization'].widget,
            employeeGroup._meta.get_field('organization').remote_field,
            admin_site,
        )

    class Meta:
        model = Campaign
        fields = (
            'organization',
            'name',
            'name_he',
            'start_date_time',
            'end_date_time',
        )
        widgets = {
            'start_date_time': forms.widgets.DateTimeInput(
                attrs={'type': 'datetime-local'}
            ),
            'end_date_time': forms.widgets.DateTimeInput(
                attrs={'type': 'datetime-local'}
            ),
        }


class EmployeeGroupCampaignForm(forms.Form):
    employee_group = forms.ModelChoiceField(queryset=EmployeeGroup.objects.all())
    budget_per_employee = forms.IntegerField()
    product_selection_mode = forms.ChoiceField(
        choices=[
            (choice.name, choice.value)
            for choice in EmployeeGroupCampaign.ProductSelectionTypeEnum
        ],
        initial=EmployeeGroupCampaign.ProductSelectionTypeEnum.SINGLE.name,
        widget=forms.Select(attrs={'onchange': 'showHideDisplayedCurrency(this);'}),
        required=False,
    )
    displayed_currency = forms.ChoiceField(
        choices=[
            (choice.name, choice.value)
            for choice in EmployeeGroupCampaign.CurrencyTypeEnum
        ],
        initial=EmployeeGroupCampaign.CurrencyTypeEnum.CURRENCY.name,
        required=False,
    )


class EmployeeForm(forms.ModelForm):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if kwargs.get('instance') and kwargs.get('instance').employee_group:
            self.fields['organization'].initial = kwargs[
                'instance'
            ].employee_group.organization

        employeeGroup = EmployeeGroup()
        self.fields['organization'].widget = RelatedFieldWidgetWrapper(
            self.fields['organization'].widget,
            employeeGroup._meta.get_field('organization').remote_field,
            admin_site,
        )

    class Meta:
        model = Employee
        fields = '__all__'


class ImportPricelistForm(forms.Form):
    xlsx = forms.FileField()

    def clean(self):
        form = super().clean()
        xlsx = form.get('xlsx')
        if not (
            xlsx
            and xlsx.content_type
            == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            and xlsx.size < 10 * 1024 * 1024
        ):
            raise forms.ValidationError(
                'import pricelist form xlsx file field is invalid'
            )
        return form


class AddCampaignProductsForm(forms.Form):
    template_name = 'campaign/product_selection.html'

    # do not filter by active products here since this queryset is the
    # validation and not the available options (that filter is at the view
    # which supplies product data to the selection page). if this is validated
    # as active only products and we select an active product for a campaign
    # and then deactivate it, the products form will never be validated and we
    # won't be able to save it
    products = forms.ModelMultipleChoiceField(queryset=Product.objects.all())


class CampaignCustomizationForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = (
            'login_page_title',
            'login_page_title_he',
            'login_page_subtitle',
            'login_page_subtitle_he',
            'main_page_first_banner_title',
            'main_page_first_banner_title_he',
            'main_page_first_banner_subtitle',
            'main_page_first_banner_subtitle_he',
            'main_page_first_banner_image',
            'main_page_first_banner_mobile_image',
            'main_page_second_banner_title',
            'main_page_second_banner_title_he',
            'main_page_second_banner_subtitle',
            'main_page_second_banner_subtitle_he',
            'main_page_second_banner_background_color',
            'main_page_second_banner_text_color',
            'sms_sender_name',
            'sms_welcome_text',
            'sms_welcome_text_he',
            'email_welcome_text',
            'email_welcome_text_he',
            'login_page_image',
            'login_page_mobile_image',
        )

        help_texts = {
            'sms_welcome_text': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`, `link`'
            ),
            'sms_welcome_text_he': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`, `link`'
            ),
            'email_welcome_text': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`'
            ),
            'email_welcome_text_he': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`'
            ),
        }


class OrderProductInlineFormset(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk is not None:
            # for existing orders filter employee group campaign product
            # choices to only ones that are related to the same campaign and
            # employee group, otherwise there will be thousands of options here
            # and the page won't even load
            self.form.base_fields[
                'product_id'
            ].queryset = EmployeeGroupCampaignProduct.objects.filter(
                employee_group_campaign_id__campaign=self.instance.campaign_employee_id.campaign,
                employee_group_campaign_id__employee_group=self.instance.campaign_employee_id.employee.employee_group,
            )
