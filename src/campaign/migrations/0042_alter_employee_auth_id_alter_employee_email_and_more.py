# Generated by Django 5.0.6 on 2024-09-05 08:14

from django.db import migrations, models

import lib.phone_utils


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0041_alter_employee_auth_id_alter_employee_email_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='auth_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='employee',
            name='email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AlterField(
            model_name='employee',
            name='phone_number',
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                validators=[lib.phone_utils.validate_phone_number],
            ),
        ),
    ]