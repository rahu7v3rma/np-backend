from dal import autocomplete
from django import forms
from django.contrib.admin import site as admin_site
from django.contrib.admin.widgets import (
    RelatedFieldWidgetWrapper,
)
from django.forms.models import BaseInlineFormSet

from campaign.models import (
    Campaign,
    Employee,
    EmployeeGroup,
    EmployeeGroupCampaign,
    EmployeeGroupCampaignProduct,
    Order,
    OrderProduct,
    Organization,
    QuickOffer,
)
from inventory.models import Product


class CampaignForm(forms.ModelForm):
    organization = forms.ModelChoiceField(queryset=Organization.objects.all())
    campaign_type = forms.ChoiceField(
        choices=[
            (Campaign.CampaignTypeEnum.NORMAL.name, 'Normal'),
            (Campaign.CampaignTypeEnum.WALLET.name, 'Wallet'),
        ],
        initial=Campaign.CampaignTypeEnum.NORMAL.value,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        employeeGroup = EmployeeGroup()
        self.fields['organization'].widget = RelatedFieldWidgetWrapper(
            self.fields['organization'].widget,
            employeeGroup._meta.get_field('organization').remote_field,
            admin_site,
        )

        self.fields['tags'].required = False
        # Add wrapper for tags field
        self.fields['tags'].widget = RelatedFieldWidgetWrapper(
            self.fields['tags'].widget,
            Campaign._meta.get_field('tags').remote_field,
            admin_site,
            can_add_related=True,
            can_change_related=True,
        )

        # If editing existing campaign, initialize tags
        if self.instance.pk:
            self.initial['tags'] = self.instance.tags.all()

    def save(self, commit=True):
        campaign = super().save(commit=False)

        if commit:
            campaign.save()
            self.save_m2m()  # Save tags relationship

        return campaign

    class Meta:
        model = Campaign
        fields = (
            'organization',
            'name',
            'name_he',
            'campaign_type',
            'start_date_time',
            'end_date_time',
            'tags',  # Added tags to fields
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
    default_discount = forms.ChoiceField(
        choices=[
            (choice.name, choice.value)
            for choice in EmployeeGroupCampaign.DefaultDiscountTypeEnum
        ],
        initial=EmployeeGroupCampaign.DefaultDiscountTypeEnum.ORGANIZATION.name,
        required=False,
    )
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
    check_out_location = forms.ChoiceField(
        choices=[
            (choice.name, choice.value)
            for choice in EmployeeGroupCampaign.CheckoutLocationTypeEnum
        ],
        initial=EmployeeGroupCampaign.CheckoutLocationTypeEnum.ISRAEL.name,
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

    # campaign_data is a stringified json representation of the selected
    # products, their discount mode and rates. the structure is:
    # {
    #    "selected_products": [1, 2, 3, ...],
    #    "discount_modes": {
    #      "1": "ORGANIZATION",
    #      ...
    #    },
    #    "discount_rates": {
    #      "1": 10,
    #      ...
    #    }
    # }
    campaign_data = forms.CharField()


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


class OrderProductInlineForm(forms.ModelForm):
    class Meta:
        model = OrderProduct
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if getattr(self.instance, 'pk', None):
            order_product: OrderProduct = self.instance
            if not order_product.product_id.active:
                self.fields['product_id'].disabled = True
                self.fields['quantity'].disabled = True
        else:
            self.fields['product_id'].queryset = self.fields[
                'product_id'
            ].queryset.filter(active=True)


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


class ImportEmployeeGroupForm(forms.Form):
    employee_group_file = forms.FileField(label='Employee Group XLSX File')

    def clean(self):
        form = super().clean()
        xlsx = form.get('employee_group_file')
        if not (
            xlsx
            and xlsx.content_type
            == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            and xlsx.size < 10 * 1024 * 1024
        ):
            raise forms.ValidationError(
                'import employee group form xlsx file field is invalid'
            )
        return form


class EmployeeGroupForm(forms.ModelForm):
    class Meta:
        model = EmployeeGroup
        fields = '__all__'


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'
        widgets = {
            'campaign_employee_id': autocomplete.ModelSelect2(
                url='campaign-employee-autocomplete'
            )
        }


class QuickOfferForm(forms.ModelForm):
    class Meta:
        model = QuickOffer
        fields = (
            'organization',
            'name',
            'name_he',
            'auth_method',
            'phone_number',
            'email',
            'auth_id',
            'tags',
            'nicklas_status',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tags'].widget = RelatedFieldWidgetWrapper(
            self.fields['tags'].widget,
            self.instance._meta.get_field('tags').remote_field,
            admin_site,
        )
        self.fields['organization'].widget = RelatedFieldWidgetWrapper(
            self.fields['organization'].widget,
            self.instance._meta.get_field('organization').remote_field,
            admin_site,
        )


class AddQuickOfferProductsForm(forms.Form):
    template_name = 'quick_offer/product_selection.html'
    products = forms.ModelMultipleChoiceField(queryset=Product.objects.all())


class QuickOfferCustomizationForm(forms.ModelForm):
    sms_sender_name = forms.CharField(required=False)
    sms_welcome_text = forms.CharField(required=False)
    email_welcome_text = forms.CharField(required=False)

    class Meta:
        model = QuickOffer
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
