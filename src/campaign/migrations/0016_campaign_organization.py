# Generated by Django 5.0.3 on 2024-06-09 18:16

from django.db import migrations, models
import django.db.models.deletion


def backfill_organizations(apps, schema_editor):
    # backfill campaign organizations by using their employee group campaign
    # related objects if any exist, or otherwise by using the first exsiting
    # organization
    Campaign = apps.get_model('campaign', 'Campaign')
    EmployeeGroupCampaign = apps.get_model('campaign', 'EmployeeGroupCampaign')
    Organization = apps.get_model('campaign', 'Organization')

    for c in Campaign.objects.all():
        egc = EmployeeGroupCampaign.objects.filter(campaign=c).first()

        if egc:
            c.organization = egc.employee_group.organization
        else:
            c.organization = Organization.objects.first()

        c.save()


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0015_remove_order_group_campaign_product_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='organization',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='campaign.organization',
            ),
        ),
        migrations.RunPython(backfill_organizations),
        migrations.AlterField(
            model_name='campaign',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='campaign.organization'
            ),
        ),
    ]
