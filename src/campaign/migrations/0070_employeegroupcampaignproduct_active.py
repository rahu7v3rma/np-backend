# Generated by Django 5.0.6 on 2025-02-28 12:55

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0069_orderproduct_po_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeegroupcampaignproduct',
            name='active',
            field=models.BooleanField(default=True),
        ),
    ]
