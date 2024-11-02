from modeltranslation.translator import TranslationOptions, translator

from .models import Campaign, QuickOffer


# for Capmaign model
class CampaignTranslationOptions(TranslationOptions):
    fields = (
        'name',
        'login_page_title',
        'login_page_subtitle',
        'main_page_first_banner_title',
        'main_page_first_banner_subtitle',
        'main_page_second_banner_title',
        'main_page_second_banner_subtitle',
        'sms_welcome_text',
        'email_welcome_text',
    )


class QuickOfferTranslationOptions(TranslationOptions):
    fields = (
        'name',
        'login_page_title',
        'login_page_subtitle',
        'main_page_first_banner_title',
        'main_page_first_banner_subtitle',
        'main_page_second_banner_title',
        'main_page_second_banner_subtitle',
        'sms_welcome_text',
        'email_welcome_text',
    )


translator.register(Campaign, CampaignTranslationOptions)
translator.register(QuickOffer, QuickOfferTranslationOptions)
