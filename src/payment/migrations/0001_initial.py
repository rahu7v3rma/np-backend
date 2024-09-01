# Generated by Django 5.0.3 on 2024-05-28 06:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('campaign', '0009_employee_otp_secret'),
        ('inventory', '0011_rename_brand_id_product_brand_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentInformation',
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
                ('amount', models.IntegerField()),
                ('process_id', models.IntegerField()),
                ('process_token', models.CharField(max_length=255)),
                ('payment_date', models.DateField(auto_now_add=True)),
                (
                    'transaction_id',
                    models.CharField(
                        blank=True, default=None, max_length=255, null=True
                    ),
                ),
                (
                    'transaction_token',
                    models.CharField(
                        blank=True, default=None, max_length=255, null=True
                    ),
                ),
                (
                    'asmachta',
                    models.CharField(
                        blank=True, default=None, max_length=255, null=True
                    ),
                ),
                ('is_paid', models.BooleanField(default=False)),
                (
                    'employee',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='campaign.employee',
                    ),
                ),
                (
                    'product',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='inventory.product',
                    ),
                ),
            ],
        ),
    ]