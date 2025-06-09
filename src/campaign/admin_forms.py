from dal import autocomplete
from django import forms
from django.contrib import admin
from django.contrib.admin import site as admin_site
from django.contrib.admin.widgets import (
    AutocompleteSelect,
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
from logistics.models import PurchaseOrderProduct


class CampaignForm(forms.ModelForm):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        widget=autocomplete.ModelSelect2(url='organization-autocomplete'),
    )
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
    employee_group = forms.ModelChoiceField(
        queryset=EmployeeGroup.objects.all(),
        widget=autocomplete.ModelSelect2(url='employee-group-autocomplete'),
    )
    default_discount = forms.ChoiceField(
        choices=[
            (choice.name, choice.value)
            for choice in EmployeeGroupCampaign.DefaultDiscountTypeEnum
        ],
        initial=EmployeeGroupCampaign.DefaultDiscountTypeEnum.ORGANIZATION.name,
        required=False,
    )
    budget_per_employee = forms.IntegerField(label='Employee Credit')
    company_cost_per_employee = forms.IntegerField(
        label='Company Cost Per Employee', initial=0
    )
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
        queryset=Organization.objects.all(),
        required=False,
        widget=autocomplete.ModelSelect2(url='organization-autocomplete'),
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
        widgets = {
            'employee_group': autocomplete.ModelSelect2(
                url='employee-group-autocomplete'
            )
        }


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
                '`organization_name`, `campaign_name`, `link`, `auth_id`'
            ),
            'sms_welcome_text_he': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`, `link`, `auth_id`'
            ),
            'email_welcome_text': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`, `link`, `auth_id`'
            ),
            'email_welcome_text_he': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`, `link`, `auth_id`'
            ),
        }


class OrderProductInlineForm(forms.ModelForm):
    class Meta:
        model = OrderProduct
        fields = ['product_id', 'quantity', 'purchase_order_product']
        widgets = {
            'purchase_order_product': AutocompleteSelect(
                PurchaseOrderProduct._meta.get_field('order_products').remote_field,
                admin_site=admin.site,
                attrs={'style': 'width: 100%'},
                choices=[],
            ),
            'product_id': AutocompleteSelect(
                EmployeeGroupCampaignProduct._meta.get_field(
                    'orderproduct'
                ).remote_field,
                admin_site=admin.site,
                attrs={'style': 'width: 100%'},
                choices=[],
            ),
        }

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

    def save_new(self, form, commit=True):
        """
        Save a new OrderProduct instance, safely populating SKU and supplier.

        This method:
        - Calls the parent's save_new(form, commit=False) to instantiate without
            immediately writing to the database.
        - Safely navigates through `instance.product_id` and its nested
            `product_id` relation, guarding against missing attributes.
        - If the nested product exists, copies over its `sku` and, if present,
            its supplier's `name`; otherwise leaves those fields blank.
        - Optionally commits the instance to the database.

        Args:
            form (Form): The ModelForm being saved.
            commit (bool, optional): If True, saves the instance after populating
                                    SKU and supplier. Defaults to True.

        Returns:
            OrderProduct: The newly saved instance, with `.sku` and `.supplier`
                        set when available.
        """
        # Instantiate without saving to the DB
        instance = super().save_new(form, commit=False)

        # Safely retrieve the related product objects
        product_rel = getattr(instance, 'product_id', None)
        nested_product = (
            getattr(product_rel, 'product_id', None) if product_rel else None
        )

        if nested_product:
            # Populate SKU
            instance.sku = nested_product.sku
            # Populate supplier name if available
            supplier_rel = getattr(nested_product, 'supplier', None)
            instance.supplier = (
                getattr(supplier_rel, 'name', '') if supplier_rel else ''
            )

        if commit:
            instance.save()
        return instance


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
        widgets = {
            'organization': autocomplete.ModelSelect2(url='organization-autocomplete')
        }


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'
        widgets = {
            'campaign_employee_id': autocomplete.ModelSelect2(
                url='campaign-employee-autocomplete'
            )
        }


class OrderProductForm(forms.ModelForm):
    class Meta:
        model = OrderProduct
        fields = '__all__'
        widgets = {
            'product_id': autocomplete.ModelSelect2(
                url='employee-group-campaign-product-autocomplete'
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
        widgets = {
            'organization': autocomplete.ModelSelect2(url='organization-autocomplete')
        }

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
    products = forms.CharField()


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
                '`organization_name`, `campaign_name`, `link`, `auth_id`'
            ),
            'sms_welcome_text_he': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`, `link`, `auth_id`'
            ),
            'email_welcome_text': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`, `link`, `auth_id`'
            ),
            'email_welcome_text_he': (
                'Use `{{ variable }}` to add dynamic values to your text. '
                'Available variables: `first_name`, `last_name`, '
                '`organization_name`, `campaign_name`, `link`, `auth_id`'
            ),
        }
