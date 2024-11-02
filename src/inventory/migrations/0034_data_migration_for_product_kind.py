# Written by Hassam on 2024-09-04

from django.db import migrations


def update_records(apps, schema_editor):
    product_model = apps.get_model('inventory', 'Product')
    tag_model = apps.get_model('inventory', 'Tag')
    tag_product_model = apps.get_model('inventory', 'TagProduct')

    tag_obj, created = tag_model.objects.get_or_create(
        name_en='Bundle', name_he='Bundle'
    )

    bundle = 'BUNDLE'
    physical = 'PHYSICAL'

    for product in product_model.objects.filter(product_kind=bundle):
        product.product_kind = physical
        product.save()
        tag_product_model.objects.get_or_create(tag_id=tag_obj, product_id=product)


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0033_data_migration_for_product_quantity'),
    ]

    operations = [
        migrations.RunPython(update_records),
    ]
