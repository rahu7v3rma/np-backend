from datetime import datetime, timezone
from io import BytesIO
import logging
import os
import uuid

from celery import shared_task
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db.models.sql.query import Query
from openpyxl import Workbook

from campaign.models import (
    Campaign,
    EmployeeGroupCampaignProduct,
)
from services.email import (
    send_export_download_email,
)

from .models import (
    Product,
    ProductColorVariationImage,
    ProductTextVariation,
    Variation,
)


logger = logging.getLogger(__name__)


def active_campaigns(obj):
    campaign_ids = EmployeeGroupCampaignProduct.objects.filter(
        product_id=obj
    ).values_list('employee_group_campaign_id__campaign', flat=True)
    campaigns = Campaign.objects.filter(
        id__in=campaign_ids, status=Campaign.CampaignStatusEnum.ACTIVE.name
    ).values_list('name', flat=True)
    active_campaign_str = ', '.join(campaigns)
    return active_campaign_str


# must use pickle task serializer for the query argument
@shared_task(serializer='pickle')
def export_products_as_xlsx(
    products_query: Query,
    exporter_user_id: int,
    exporter_email: str,
    base_export_download_url: str,
) -> bool:
    """
    Export all queried products as an xlsx file. This method retuns a
    HttpResponse which can be returned as-is by actions
    """

    export_init_datetime = datetime.now(timezone.utc)

    # restoring the Order model queryset as described in the docs -
    # https://docs.djangoproject.com/en/5.1/ref/models/querysets/#pickling-querysets
    products_queryset = Product.objects.all()
    products_queryset.query = products_query

    field_names = [
        'id',
        'brand',
        'supplier',
        'reference',
        'name_en',
        'name_he',
        'product_kind',
        'voucher_type',
        'client_discount_rate',
        'supplier_discount_rate',
        'product_type',
        'description_en',
        'description_he',
        'sku',
        'link',
        'active',
        'cost_price',
        'delivery_price',
        'logistics_rate_cost_percent',
        'total_cost',
        'google_price',
        'sale_price',
        'technical_details_en',
        'technical_details_he',
        'warranty_en',
        'warranty_he',
        'exchange_value',
        'exchange_policy_en',
        'exchange_policy_he',
        'categories',
        'tags',
        'active_campaigns',
        'product_quantity',
    ]

    variation_names = set()
    for product in products_queryset:
        for product_variation in product.productvariation_set.all():
            variation = product_variation.variation
            variation_names.add(variation.site_name)

    variation_names = sorted(variation_names)

    field_names = field_names[:13] + variation_names + field_names[13:]

    workbook = Workbook()
    worksheet = workbook.active

    worksheet.append(field_names)

    for product in products_queryset:
        row_data = [
            product.id,
            product.brand.name,
            product.supplier.name,
            product.reference,
            product.name_en,
            product.name_he,
            product.product_kind,
            product.voucher_type,
            product.client_discount_rate,
            product.supplier_discount_rate,
            product.product_type,
            product.description_en,
            product.description_he,
        ]
        variation_data = {variation: [] for variation in variation_names}
        if product.product_kind == Product.ProductKindEnum.VARIATION.name:
            for product_variation in product.productvariation_set.all():
                variation = product_variation.variation
                if variation.variation_kind == Variation.VariationKindEnum.COLOR.name:
                    color_images = ProductColorVariationImage.objects.filter(
                        product_variation=product_variation
                    )
                    for color_image in color_images:
                        color_name = color_image.color.name
                        variation_data[variation.site_name].append(color_name)

                elif variation.variation_kind == Variation.VariationKindEnum.TEXT.name:
                    text_variations = ProductTextVariation.objects.filter(
                        product_variation=product_variation
                    )
                    for text_variation in text_variations:
                        text_value = text_variation.text.text
                        variation_data[variation.site_name].append(text_value)

        row_data.extend(
            ', '.join(variation_data.get(name, [])) for name in variation_names
        )

        row_data.extend(
            [
                product.sku,
                product.link,
                product.active,
                product.cost_price,
                product.delivery_price,
                product.logistics_rate_cost_percent,
                product.total_cost,
                product.google_price,
                product.sale_price,
                product.technical_details_en,
                product.technical_details_he,
                product.warranty_en,
                product.warranty_he,
                product.exchange_value,
                product.exchange_policy_en,
                product.exchange_policy_he,
                ', '.join(category.name for category in product.categories.all()),
                ', '.join(tag.name for tag in product.tags.all()),
                active_campaigns(obj=product),
                product.product_quantity,
            ]
        )

        worksheet.append(row_data)

    storage = storages['exports']
    formatted_init_datetime = export_init_datetime.strftime('%Y_%m_%d_%H%M')

    export_file_name = storage.generate_filename(
        os.path.join(
            str(uuid.uuid4()),
            f'products_export_{formatted_init_datetime}.xlsx',
        ),
    )

    private_export_file_name = storage.generate_filename(
        os.path.join(
            str(exporter_user_id),
            export_file_name,
        ),
    )

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    storage.save(private_export_file_name, ContentFile(buffer.read()))

    send_export_download_email(
        'product', exporter_email, f'{base_export_download_url}{export_file_name}'
    )

    return True
