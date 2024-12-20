# Generated by Django 5.0.3 on 2024-06-10 08:18

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0016_campaign_organization'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employeegroupcampaign',
            name='auth_method',
            field=models.CharField(
                choices=[('EMAIL', 'email'), ('SMS', 'sms'), ('AUTH_ID', 'auth_id')],
                default='SMS',
                max_length=50,
            ),
        ),
    ]
