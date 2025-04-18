# Generated by Django 5.0.6 on 2024-08-30 12:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0028_alter_product_sale_price'),
    ]

    operations = [
        migrations.CreateModel(
            name='BrandSupplier',
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
                (
                    'brand',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='inventory.brand',
                    ),
                ),
                (
                    'supplier',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='inventory.supplier',
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name='brand',
            name='suppliers',
            field=models.ManyToManyField(
                through='inventory.BrandSupplier', to='inventory.supplier'
            ),
        ),
        migrations.AddField(
            model_name='supplier',
            name='brands',
            field=models.ManyToManyField(
                through='inventory.BrandSupplier', to='inventory.brand'
            ),
        ),
    ]
