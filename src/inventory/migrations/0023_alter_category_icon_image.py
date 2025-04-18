# Generated by Django 5.0.6 on 2024-07-05 13:56

from django.db import migrations

import lib.storage


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0022_remove_product_total_cost'),
    ]

    operations = [
        migrations.AlterField(
            model_name='category',
            name='icon_image',
            field=lib.storage.RandomNameImageFieldSVG(
                blank=True,
                null=True,
                upload_to=lib.storage.RandomNameImageFieldSVG._generate_random_file_name,
            ),
        ),
    ]
