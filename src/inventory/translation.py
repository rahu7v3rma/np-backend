from modeltranslation.translator import TranslationOptions, translator

from campaign.models import Employee, Organization
from inventory.models import (
    Brand,
    Category,
    Product,
    Supplier,
    Tag,
    TextVariation,
    Variation,
)


class ProductTranslationOptions(TranslationOptions):
    fields = (
        'name',
        'description',
        'technical_details',
        'warranty',
        'exchange_policy',
        'offer',
    )

    # name is required in all translation languages
    required_languages = {'default': ('name',)}


class BrandTranslationOptions(TranslationOptions):
    fields = ('name',)


class SupplierTranslationOptions(TranslationOptions):
    fields = ('name', 'address_city', 'address_street', 'address_street_number')

    required_languages = {'default': ('name',)}


class CategoryTranslationOptions(TranslationOptions):
    fields = ('name',)
    required_languages = {'default': ('name',)}


class TagTranslationOptions(TranslationOptions):
    fields = ('name',)


class OrganizationTranslationOptions(TranslationOptions):
    fields = ('name',)


class EmployeeTranslationOptions(TranslationOptions):
    fields = (
        'first_name',
        'last_name',
    )
    required_languages = {'default': ('first_name', 'last_name')}


class VariationTranslationOptions(TranslationOptions):
    fields = ('system_name', 'site_name')


class TextVariationTranslationOptions(TranslationOptions):
    fields = ('text',)


translator.register(Product, ProductTranslationOptions)
translator.register(Brand, BrandTranslationOptions)
translator.register(Supplier, SupplierTranslationOptions)
translator.register(Category, CategoryTranslationOptions)
translator.register(Tag, TagTranslationOptions)
translator.register(Organization, OrganizationTranslationOptions)
translator.register(Employee, EmployeeTranslationOptions)
translator.register(Variation, VariationTranslationOptions)
translator.register(TextVariation, TextVariationTranslationOptions)
