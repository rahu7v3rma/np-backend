from django.template import Context, Template

from campaign.models import Campaign, Employee


def fill_message_template(welcome_text, employee: Employee, campaign: Campaign) -> str:
    if employee.default_language == 'HE':
        context = {
            'first_name': employee.first_name_he,
            'last_name': employee.last_name_he,
            'organization_name': campaign.organization.name_he,
            'campaign_name': campaign.name_he,
            'link': employee.get_campaign_site_link(campaign.code),
            'auth_id': employee.auth_id,
        }
    else:
        context = {
            'first_name': employee.first_name_en,
            'last_name': employee.last_name_en,
            'organization_name': campaign.organization.name_en,
            'campaign_name': campaign.name_en,
            'link': employee.get_campaign_site_link(campaign.code),
            'auth_id': employee.auth_id,
        }
    message_text = Template(welcome_text).render(Context(context))
    return message_text


def fill_message_template_email(employee: Employee, campaign: Campaign) -> str:
    if employee.default_language == 'HE':
        return fill_message_template(
            welcome_text=campaign.email_welcome_text_he,
            employee=employee,
            campaign=campaign,
        )
    else:
        return fill_message_template(
            welcome_text=campaign.email_welcome_text_en,
            employee=employee,
            campaign=campaign,
        )


def fill_message_template_sms(employee: Employee, campaign: Campaign) -> str:
    if employee.default_language == 'HE':
        return fill_message_template(
            welcome_text=campaign.sms_welcome_text_he,
            employee=employee,
            campaign=campaign,
        )
    else:
        return fill_message_template(
            welcome_text=campaign.sms_welcome_text_en,
            employee=employee,
            campaign=campaign,
        )
