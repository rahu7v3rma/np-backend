import secrets

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import (
    Campaign,
    CampaignEmployee,
    Employee,
    EmployeeAuthEnum,
    EmployeeGroupCampaign,
)
from .tasks import (
    send_campaign_welcome_message_email,
    send_campaign_welcome_message_sms,
)


@receiver(pre_save, sender=Campaign)
def create_campaign_code(sender, instance, **kwargs):
    # generate the campaign code only if a code has not been generated yet
    if not instance.code:
        instance.code = secrets.token_hex(8)


@receiver(post_save, sender=Employee)
def connect_employee_to_active_campaigns(sender, instance, **kwargs):
    active_campaigns = instance.employee_group.campaigns.filter(
        status=Campaign.CampaignStatusEnum.ACTIVE.name
    ).all()

    for campaign in active_campaigns:
        # create campaign employee instances if the employee's active
        # campaigns have changed (for instance, if we created an employee
        # in a group with an active campaign)
        _, created = CampaignEmployee.objects.get_or_create(
            campaign=campaign, employee=instance
        )

        # if the employee was not part of this campaign yet send a welcome
        # message
        if created:
            employee_grp_campaign = EmployeeGroupCampaign.objects.filter(
                campaign=campaign, employee_group=instance.employee_group
            ).first()

            if instance.employee_group.auth_method == EmployeeAuthEnum.EMAIL.name:
                send_campaign_welcome_message_email.apply_async(
                    (instance.id, employee_grp_campaign.id, campaign.id)
                )
            elif instance.employee_group.auth_method == EmployeeAuthEnum.SMS.name:
                send_campaign_welcome_message_sms.apply_async(
                    (instance.id, employee_grp_campaign.id, campaign.id)
                )
