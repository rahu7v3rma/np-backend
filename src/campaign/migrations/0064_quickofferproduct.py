# Generated by Django 5.0.6 on 2025-01-23 11:37

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


def populate_quick_offer_products(apps, schema_editor):
    QuickOfferProduct = apps.get_model('campaign', 'QuickOfferProduct')
    QuickOffer = apps.get_model('campaign', 'QuickOffer')
    for quick_offer in QuickOffer.objects.all():
        for quick_offer_product in quick_offer.products.all():
            QuickOfferProduct.objects.get_or_create(
                quick_offer=quick_offer,
                product=quick_offer_product,
            )
        quick_offer.products.clear()


def reverse_quick_offer_products(apps, schema_editor):
    QuickOfferProduct = apps.get_model('campaign', 'QuickOfferProduct')
    QuickOffer = apps.get_model('campaign', 'QuickOffer')
    for quick_offer in QuickOffer.objects.all():
        for quick_offer_product in QuickOfferProduct.objects.filter(
            quick_offer=quick_offer
        ).all():
            quick_offer.products.add(quick_offer_product.product)
            quick_offer.save()


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0063_remove_employee_total_budget_and_more'),
        ('inventory', '0050_alter_brand_name_alter_brand_name_en_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='QuickOfferProduct',
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
                    'organization_discount_rate',
                    models.FloatField(
                        blank=True,
                        help_text='Enter a Organization Discount Rate up to 100.0.',
                        null=True,
                        validators=[django.core.validators.MaxValueValidator(100.0)],
                    ),
                ),
                (
                    'product',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='inventory.product',
                    ),
                ),
                (
                    'quick_offer',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='campaign.quickoffer',
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            populate_quick_offer_products, reverse_quick_offer_products
        ),
    ]
