# Generated by Django 5.0.6 on 2024-08-27 14:31

from django.db import migrations


def update_records(apps, schema_editor):
    product_model = apps.get_model('inventory', 'Product')

    for product in product_model.objects.filter(product_quantity=0).all():
        product.product_quantity = 2147483647
        product.save()


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0032_data_migration_for_product_brand_supplier'),
    ]

    operations = [
        migrations.RunPython(update_records),
    ]