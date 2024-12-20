# Generated by Django 5.0.3 on 2024-04-30 15:18

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0005_alter_campaign_banner_image_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='description_en',
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name='campaign',
            name='description_he',
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name='campaign',
            name='name_en',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='campaign',
            name='name_he',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
