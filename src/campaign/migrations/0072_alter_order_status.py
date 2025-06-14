# Generated by Django 5.0.6 on 2025-03-09 10:44

from django.db import migrations, models

import campaign.models


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0071_remove_orderproduct_po_status_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('INCOMPLETE', 'Incomplete'),
                    ('PENDING', 'Pending'),
                    ('CANCELLED', 'Cancelled'),
                    ('SENT_TO_LOGISTIC_CENTER', 'Sent To Logistic Center'),
                    ('COMPLETE', 'Complete'),
                ],
                default=campaign.models.Order.OrderStatusEnum['INCOMPLETE'],
                max_length=50,
            ),
        ),
    ]
