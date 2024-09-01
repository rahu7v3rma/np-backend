# Generated by Django 5.0.6 on 2024-07-23 16:48

from django.db import migrations, models
import django.db.models.deletion

import logistics.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('inventory', '0023_alter_category_icon_image'),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseOrderProduct',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('quantity_ordered', models.PositiveIntegerField()),
                ('quantity_in_transit', models.PositiveIntegerField()),
                ('quantity_in_dc', models.PositiveIntegerField()),
                (
                    'product_id',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='inventory.product',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('notes', models.TextField()),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('PENDING', 'Pending'),
                            ('SENT_TO_SUPPLIER', 'Sent to supplier'),
                            ('APPROVED', 'Approved'),
                            ('CANCELLED', 'Cancelled'),
                        ],
                        default=logistics.models.PurchaseOrder.Status['PENDING'],
                        max_length=100,
                    ),
                ),
                (
                    'supplier',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='inventory.supplier',
                    ),
                ),
                (
                    'products',
                    models.ManyToManyField(to='logistics.purchaseorderproduct'),
                ),
            ],
        ),
        migrations.CreateModel(
            name='PurchaseOrderSentLog',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('sent_datetime', models.DateTimeField()),
                (
                    'purchase_order',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='logistics.purchaseorder',
                    ),
                ),
            ],
        ),
    ]