# Generated by Django 5.0.3 on 2024-05-10 16:42

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0008_organizationaddress_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='otp_secret',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
