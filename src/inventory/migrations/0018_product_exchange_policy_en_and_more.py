# Generated by Django 5.0.3 on 2024-06-16 14:18

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0017_product_product_kind'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='exchange_policy_en',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='exchange_policy_he',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='technical_details_en',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='technical_details_he',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='warranty_en',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='warranty_he',
            field=models.TextField(blank=True, null=True),
        ),
    ]
