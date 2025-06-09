from datetime import datetime, timezone
from io import BytesIO
import json
import logging
import os
import uuid

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db.models import Q
from django.db.models.sql.query import Query
from openpyxl import Workbook
import pytz

from campaign.models import Order
from inventory.models import Product, Variation
from services.email import send_export_download_email, send_purchase_order_email

from .enums import LogisticsCenterEnum, LogisticsCenterMessageTypeEnum
from .models import EmployeeOrderProduct, LogisticsCenterMessage, PurchaseOrder
from .providers.orian import (
    add_or_update_dummy_customer as orian_add_or_update_dummy_customer,
    add_or_update_inbound as orian_add_or_update_inbound,
    add_or_update_outbound as orian_add_or_update_outbound,
    add_or_update_product as orian_add_or_update_product,
    add_or_update_supplier as orian_add_or_update_supplier,
    handle_logistics_center_inbound_receipt_message as orian_handle_logistics_center_inbound_receipt_message,  # noqa: E501
    handle_logistics_center_order_status_change_message as orian_handle_logistics_center_order_status_change_message,  # noqa: E501
    handle_logistics_center_ship_order_message as orian_handle_logistics_center_ship_order_message,  # noqa: E501
    process_logistics_center_snapshot_file as orian_process_logistics_center_snapshot_file,  # noqa: E501
    sync_logistics_center_snapshot_files as orian_sync_logistics_center_snapshot_files,
)
from .providers.pick_and_pack import (
    add_or_update_inbound as pick_and_pack_add_or_update_inbound,
    add_or_update_outbound as pick_and_pack_add_or_update_outbound,
    handle_logistics_center_inbound_receipt_message as pick_and_pack_handle_logistics_center_inbound_receipt_message,  # noqa: E501
    handle_logistics_center_inbound_status_change_message as pick_and_pack_handle_logistics_center_inbound_status_change_message,  # noqa: E501
    handle_logistics_center_order_status_change_message as pick_and_pack_handle_logistics_center_order_status_change_message,  # noqa: E501
    handle_logistics_center_ship_order_message as pick_and_pack_handle_logistics_center_ship_order_message,  # noqa: E501
    handle_logistics_center_snapshot_message as pick_and_pack_handle_logistics_center_snapshot_message,  # noqa: E501
)
from .utils import snake_to_title


logger = logging.getLogger(__name__)


@shared_task
def send_purchase_orders_to_supplier(po_ids=[]):
    logger.info(
        f'sending puchase order emails to suppliers for purchase order IDs {po_ids}...'
    )
    purchase_orders = PurchaseOrder.objects.filter(id__in=po_ids)

    for purchase_order in purchase_orders:
        logger.info(f'sending email to {purchase_order.id}...')
        send_purchase_order_to_supplier.apply_async((purchase_order.pk, 'he'))
        logger.info(f'sent email to {purchase_order.id}')

    logger.info('done sending puchase order emails to suppliers')


@shared_task
def send_purchase_order_to_supplier(order_id: int, language_code: str) -> bool:
    order: PurchaseOrder = PurchaseOrder.objects.filter(id=order_id).first()
    products = order.products.all()
    products_data = []
    sub_total = 0
    for _product in products:
        _category = _product.product_id.categories.all().first()
        _category = _category.name if _category else ''
        _brand = _product.product_id.brand.name
        cost_price = round(
            _product.product_id.cost_price / ((100 + settings.TAX_PERCENT) / 100), 2
        )
        if _product.product_id.product_kind == Product.ProductKindEnum.MONEY.name:
            cost_price = int(cost_price)
        total_price = cost_price * _product.quantity_ordered
        products_data.append(
            {
                'id': _product.product_id.id,
                'main': _product.product_id.main_image_link,
                'name': _product.product_id.name_he,
                'category': _category,
                'brand': _brand,
                'quantity': _product.quantity_ordered,
                'quantity_received': 0,
                'sku': _product.product_id.sku,
                'barcode': _product.product_id.reference,
                'cost_price': cost_price,
                'status': order.status,
                'supplier': _product.product_id.supplier.name,
                'total_price': total_price,
            }
        )

        sub_total += total_price

    column_headers = snake_to_title(list(products_data[0].keys()))

    workbook = Workbook()
    xlsx = workbook.active
    xlsx.append(column_headers)

    for product_idx, _product in enumerate(products_data):
        row = list(_product.values())
        xlsx.append(row)

    xlsx.append([])
    xlsx.append(['Description', 'Total Price'])
    xlsx.append([order.notes, sub_total])

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    attachment = {
        'filename': f'Order_Products_{order.id}.xlsx',
        'content': output.getvalue(),
        'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }

    return send_purchase_order_email(order, attachment, language_code)


@shared_task(
    autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 30}
)
def send_purchase_order_to_logistics_center(
    purchase_order_id: int, center: LogisticsCenterEnum
) -> bool:
    logger.info(f'Sending purchase order {purchase_order_id} to logistics center...')

    purchase_order = PurchaseOrder.objects.get(id=purchase_order_id)

    if purchase_order.status == PurchaseOrder.Status.APPROVED.name:
        # the purchase order was approved since this task was queued, so we can
        # just exit
        logger.info(f'Purchase order {purchase_order_id} is already approved')
        return True

    logger.info('Syncing supplier data with logistics center')

    # make sure supplier (company) is created if the center requires so
    if center == LogisticsCenterEnum.ORIAN:
        if not orian_add_or_update_supplier(purchase_order.supplier):
            raise Exception('Failed to add or update supplier!')

    logger.info('Syncing product data with logistics center')

    # make sure products (skus) are created if the center requires so
    if center == LogisticsCenterEnum.ORIAN:
        for product in purchase_order.products:
            if not orian_add_or_update_product(product.product_id):
                raise Exception('Failed to add or update product!')

    logger.info('Sending inbound request to logistics center')

    # create inbound with the date in the logsitics center's timezone
    if center == LogisticsCenterEnum.ORIAN:
        if not orian_add_or_update_inbound(
            purchase_order,
            datetime.now(pytz.timezone(settings.ORIAN_MESSAGE_TIMEZONE_NAME)),
        ):
            raise Exception('Failed to add or update inbound!')
    elif center == LogisticsCenterEnum.PICK_AND_PACK:
        if not pick_and_pack_add_or_update_inbound(
            purchase_order,
            datetime.now(pytz.timezone(settings.PAP_MESSAGE_TIMEZONE_NAME)),
        ):
            raise Exception('Failed to add or update inbound!')

    # update quantity in transit and sent at fields
    for product in purchase_order.products:
        product.quantity_sent_to_logistics_center = product.quantity_ordered
        product.save(update_fields=['quantity_sent_to_logistics_center'])

    # update purchase order status and sent timestamp
    purchase_order.status = PurchaseOrder.Status.APPROVED.name
    purchase_order.sent_to_logistics_center_at = datetime.now()

    # use this flag to let the pre-save signal know this change is made from
    # the right place
    purchase_order._approved_by_func = True
    purchase_order.save(update_fields=['status', 'sent_to_logistics_center_at'])
    delattr(purchase_order, '_approved_by_func')

    logger.info(
        f'Successfully sent purchase order {purchase_order_id} to logistics center!'
    )

    return True


@shared_task(
    autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 30}
)
def send_order_to_logistics_center(order_id: int, center: LogisticsCenterEnum) -> bool:
    logger.info(f'Sending order {order_id} to logistics center...')

    order = Order.objects.get(pk=order_id)

    # sent-by-supplier and money products should not be sent to the logistics center
    order_products = list(
        filter(
            lambda op: op['product_type']
            != Product.ProductTypeEnum.SENT_BY_SUPPLIER.name
            and op['product_kind'] != Product.ProductKindEnum.MONEY.name,
            order.ordered_products(),
        )
    )

    if order.status != Order.OrderStatusEnum.PENDING.name:
        logger.warn(
            f'Order {order_id} is no longer pending. Not sending to logistics center'
        )
        return True
    elif len(order_products) == 0:
        logger.warn(
            f'Order {order_id} only contains products that are sent-by-supplier'
            'or are money products. Not sending to logistics center'
        )
        return True

    try:
        logger.info('Syncing dummy customer data with logistics center')

        if center == LogisticsCenterEnum.ORIAN:
            if not orian_add_or_update_dummy_customer():
                raise Exception('Failed to sync dummy customer data!')

        logger.info('Sending outbound request to logistics center')

        # create outbound with the date in the logsitics center's timezone
        if center == LogisticsCenterEnum.ORIAN:
            if not orian_add_or_update_outbound(
                order,
                order_products,
                datetime.now(pytz.timezone(settings.ORIAN_MESSAGE_TIMEZONE_NAME)),
            ):
                raise Exception('Failed to send outbound!')
        elif center == LogisticsCenterEnum.PICK_AND_PACK:
            if not pick_and_pack_add_or_update_outbound(
                order,
                order_products,
                datetime.now(pytz.timezone(settings.PAP_MESSAGE_TIMEZONE_NAME)),
            ):
                raise Exception('Failed to send outbound!')
    except:
        # set the order logistics center status to "Error" so this can be
        # tracked, then re-raise the exception
        order.logistics_center_status = 'Error'
        order.save(update_fields=['logistics_center_status'])

        raise

    # update order status and reset error status
    order.status = Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name
    if order.logistics_center_status == 'Error':
        order.logistics_center_status = None
    order.save(update_fields=['status', 'logistics_center_status'])

    logger.info(f'Successfully sent order {order_id} to logistics center!')

    return True


@shared_task(
    autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 30}
)
def sync_product_with_logistics_center(
    product_id: int, center: LogisticsCenterEnum
) -> bool:
    logger.info(f'Syncing product {product_id} with logistics center...')

    product = Product.objects.get(id=product_id)

    logger.info('Syncing product data with logistics center')

    # make sure products (skus) are created
    if center == LogisticsCenterEnum.ORIAN:
        if not orian_add_or_update_product(product):
            raise Exception('Failed to add or update product!')

    logger.info(f'Successfully synced product {product_id} with logistics center!')

    return True


@shared_task(
    autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 30}
)
def process_logistics_center_message(message_id: int) -> bool:
    logger.info(f'Processing logistics center message {message_id}...')

    message = LogisticsCenterMessage.objects.get(pk=message_id)

    json_body = json.loads(message.raw_body)

    if (
        message.message_type
        == LogisticsCenterMessageTypeEnum.INBOUND_STATUS_CHANGE.name
    ):
        if message.center == LogisticsCenterEnum.PICK_AND_PACK.name:
            pick_and_pack_handle_logistics_center_inbound_status_change_message(
                message, json_body['data']
            )
    elif message.message_type == LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name:
        if message.center == LogisticsCenterEnum.ORIAN.name:
            orian_handle_logistics_center_inbound_receipt_message(
                message, json_body['DATACOLLECTION']['DATA']
            )
        elif message.center == LogisticsCenterEnum.PICK_AND_PACK.name:
            pick_and_pack_handle_logistics_center_inbound_receipt_message(
                message, json_body['data']
            )
    elif (
        message.message_type == LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name
    ):
        if message.center == LogisticsCenterEnum.ORIAN.name:
            orian_handle_logistics_center_order_status_change_message(
                message, json_body['DATACOLLECTION']['DATA']
            )
        elif message.center == LogisticsCenterEnum.PICK_AND_PACK.name:
            pick_and_pack_handle_logistics_center_order_status_change_message(
                message, json_body['data']
            )
    elif message.message_type == LogisticsCenterMessageTypeEnum.SHIP_ORDER.name:
        if message.center == LogisticsCenterEnum.ORIAN.name:
            orian_handle_logistics_center_ship_order_message(
                message, json_body['DATACOLLECTION']['DATA']
            )
        elif message.center == LogisticsCenterEnum.PICK_AND_PACK.name:
            pick_and_pack_handle_logistics_center_ship_order_message(
                message, json_body['data']
            )
    elif message.message_type == LogisticsCenterMessageTypeEnum.SNAPSHOT.name:
        if message.center == LogisticsCenterEnum.PICK_AND_PACK.name:
            pick_and_pack_handle_logistics_center_snapshot_message(
                message, json_body['data']
            )
    else:
        raise Exception(f'Unknown message type: {message.message_type}')

    logger.info(f'Successfully processed logistics center message {message_id}!')
    return True


@shared_task
def sync_logistics_center_snapshot_files() -> bool:
    logger.info('Syncing with logistics center snapshots...')

    # only orian currently requires actively syncing snapshot files
    synced_snapshots = orian_sync_logistics_center_snapshot_files()

    for snapshot_file_path, snapshot_date_time in synced_snapshots:
        # call process task
        process_logistics_center_snapshot_file.apply_async(
            (LogisticsCenterEnum.ORIAN.name, snapshot_file_path, snapshot_date_time)
        )

    logger.info('Successfully synced snapshot files!')
    return True


@shared_task
def process_logistics_center_snapshot_file(
    logistics_center: str, snapshot_file_path: str, snapshot_date_time: datetime
) -> bool:
    logger.info(
        f'Processing logistics center {logistics_center} snapshot '
        f'{snapshot_file_path}...'
    )

    if logistics_center == LogisticsCenterEnum.ORIAN.name:
        return orian_process_logistics_center_snapshot_file(
            snapshot_file_path, snapshot_date_time
        )


# must use pickle task serializer for the query argument
@shared_task(serializer='pickle')
def export_order_summaries_as_xlsx_task(
    order_summaries_query: Query,
    exporter_user_id: int,
    exporter_email: str,
    base_export_download_url: str,
) -> bool:
    export_init_datetime = datetime.now(timezone.utc)

    # restoring the EmployeeOrderProduct model queryset as described in the
    # docs -
    # https://docs.djangoproject.com/en/5.1/ref/models/querysets/#pickling-querysets
    order_summaries_queryset = EmployeeOrderProduct.objects.all()
    order_summaries_queryset.query = order_summaries_query

    field_names = [
        'Name',
        'Supplier',
        'Brand',
        'SKU',
        'Color Variations',
        'Barcode',
        'Total Ordered',
        'Cost Price',
        'Saved Stock',
        'In Transit Stock',
        'DC Stock',
        'Difference To Order',
    ]

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(field_names)

    for order_summary in order_summaries_queryset.values(
        'product_name',
        'product_supplier',
        'product_brand',
        'product_sku',
        'variations',
        'product_reference',
        'total_ordered',
        'product_cost_price',
        'product_quantity',
        'in_transit_stock',
        'dc_stock',
        'difference_to_order',
    ):
        color_variation = []
        if order_summary['variations']:
            for variation_type, variation_value in order_summary['variations'].items():
                variation_instance = Variation.objects.filter(
                    Q(site_name_he=variation_type) | Q(site_name_en=variation_type)
                ).first()
                if (
                    variation_instance
                    and Variation.VariationKindEnum.COLOR.name
                    == variation_instance.variation_kind
                ):
                    color_variation.append(variation_value)

        record = [
            order_summary['product_name'],
            order_summary['product_supplier'],
            order_summary['product_brand'],
            order_summary['product_sku'],
            ', '.join(color_variation),
            order_summary['product_reference'],
            order_summary['total_ordered'],
            order_summary['product_cost_price'],
            order_summary['product_quantity'],
            order_summary['in_transit_stock'],
            order_summary['dc_stock'],
            order_summary['difference_to_order'],
        ]

        worksheet.append(record)

    storage = storages['exports']

    formatted_init_datetime = export_init_datetime.strftime('%Y_%m_%d_%H%M')
    export_file_name = storage.generate_filename(
        os.path.join(
            str(uuid.uuid4()),
            f'order_summaries_export_{formatted_init_datetime}.xlsx',
        ),
    )
    private_export_file_name = storage.generate_filename(
        os.path.join(
            str(exporter_user_id),
            export_file_name,
        ),
    )

    # save workbook to memory and then to the configured storage
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    storage.save(private_export_file_name, ContentFile(buffer.read()))

    # send an email to the exporter with a link to download the file
    send_export_download_email(
        'order summaries',
        exporter_email,
        f'{base_export_download_url}{export_file_name}',
    )

    return True
