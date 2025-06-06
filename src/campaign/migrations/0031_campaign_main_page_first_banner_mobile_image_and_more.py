# Generated by Django 5.0.6 on 2024-07-12 12:16

from django.db import migrations

import lib.storage


def copy_existing_desktop_images_to_new_mobile_images(apps, schema_editor):
    Campaign = apps.get_model('campaign', 'Campaign')
    db_alias = schema_editor.connection.alias

    for c in Campaign.objects.using(db_alias).all():
        c.main_page_first_banner_mobile_image = c.main_page_first_banner_image
        c.main_page_second_banner_mobile_image = c.main_page_second_banner_image
        c.save(
            update_fields=[
                'main_page_first_banner_mobile_image',
                'main_page_second_banner_mobile_image',
            ],
        )


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0030_order_impersonated_by'),
    ]

    # create the new fields nullable, copy existing data into them and then
    # alter them so they aren't nullable
    operations = [
        migrations.AddField(
            model_name='campaign',
            name='main_page_first_banner_mobile_image',
            field=lib.storage.RandomNameImageField(
                null=True,
                upload_to=lib.storage.RandomNameImageField._generate_random_file_name,
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='main_page_second_banner_mobile_image',
            field=lib.storage.RandomNameImageField(
                null=True,
                upload_to=lib.storage.RandomNameImageField._generate_random_file_name,
            ),
        ),
        # no reverse code since the fields will be deleted anyhow
        migrations.RunPython(copy_existing_desktop_images_to_new_mobile_images),
        migrations.AlterField(
            model_name='campaign',
            name='main_page_first_banner_mobile_image',
            field=lib.storage.RandomNameImageField(
                upload_to=lib.storage.RandomNameImageField._generate_random_file_name
            ),
        ),
        migrations.AlterField(
            model_name='campaign',
            name='main_page_second_banner_mobile_image',
            field=lib.storage.RandomNameImageField(
                upload_to=lib.storage.RandomNameImageField._generate_random_file_name
            ),
        ),
    ]
