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
from django.db import transaction
from django.db.models.sql.query import Query
from openpyxl import Workbook
import pytz
import xmltodict

from campaign.models import Order
from inventory.models import Product
from services.email import (
    send_export_download_email,
    send_purchase_order_email,
)

from .models import (
    EmployeeOrderProduct,
    LogisticsCenterEnum,
    LogisticsCenterMessage,
    LogisticsCenterMessageTypeEnum,
    LogisticsCenterStockSnapshot,
    LogisticsCenterStockSnapshotLine,
    PurchaseOrder,
)
from .providers.orian import (
    # add_or_update_dummy_customer,
    add_or_update_inbound,
    add_or_update_outbound,
    add_or_update_product,
    add_or_update_supplier,
    fetch_logistics_center_snapshots,
    handle_logistics_center_inbound_receipt_message,
    handle_logistics_center_order_status_change_message,
    handle_logistics_center_ship_order_message,
)


logger = logging.getLogger(__name__)


@shared_task
def send_purchaseorder_to_supplier(po_ids=[]):
    logger.info(f'sending welcome messages for purchase order IDs {po_ids}...')
    purchase_orders = PurchaseOrder.objects.filter(id__in=po_ids)

    for purchase_order in purchase_orders:
        logger.info('sending email to ' f'{purchase_order.id}...')
        send_purchase_order_email(purchase_order)
        logger.info(f'sent email to {purchase_order.id}')

    logger.info('done sending puchase order emails to suppliers')


@shared_task(
    autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 30}
)
def send_purchase_order_to_logistics_center(purchase_order_id: int) -> bool:
    logger.info(f'Sending purchase order {purchase_order_id} to logistics center...')

    purchase_order = PurchaseOrder.objects.get(id=purchase_order_id)

    logger.info('Syncing supplier data with logistics center')

    # make sure supplier (company) is created
    if not add_or_update_supplier(purchase_order.supplier):
        raise Exception('Failed to add or update supplier!')

    logger.info('Syncing product data with logistics center')

    # make sure products (skus) are created
    for product in purchase_order.products:
        if not add_or_update_product(product.product_id):
            raise Exception('Failed to add or update product!')

    logger.info('Sending inbound request to logistics center')

    # create inbound with the date in the logsitics center's timezone
    if not add_or_update_inbound(
        purchase_order,
        datetime.now(pytz.timezone(settings.ORIAN_MESSAGE_TIMEZONE_NAME)),
    ):
        raise Exception('Failed to add or update inbound!')

    # update quantity in transit and sent at fields
    for product in purchase_order.products:
        product.quantity_sent_to_logistics_center = product.quantity_ordered
        product.save(update_fields=['quantity_sent_to_logistics_center'])

    purchase_order.sent_to_logistics_center_at = datetime.now()
    purchase_order.save(update_fields=['sent_to_logistics_center_at'])

    logger.info(
        f'Successfully sent purchase order {purchase_order_id} to logistics center!'
    )

    return True


@shared_task(
    autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 30}
)
def send_order_to_logistics_center(order_id: int) -> bool:
    logger.info(f'Sending order {order_id} to logistics center...')

    order = Order.objects.get(pk=order_id)

    # sent-by-supplier and money products should not be sent to orian
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

    logger.info('Syncing dummy customer data with logistics center')

    # if not add_or_update_dummy_customer():
    #     raise Exception('Failed to sync dummy customer data!')

    logger.info('Sending outbound request to logistics center')

    # create outbound with the date in the logsitics center's timezone
    if not add_or_update_outbound(
        order,
        order_products,
        datetime.now(pytz.timezone(settings.ORIAN_MESSAGE_TIMEZONE_NAME)),
    ):
        raise Exception('Failed to send outbound!')

    # update order status
    order.status = Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name
    order.save(update_fields=['status'])

    logger.info(f'Successfully sent order {order_id} to logistics center!')

    return True


@shared_task(
    autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 30}
)
def sync_product_with_logistics_center(product_id: int) -> bool:
    logger.info(f'Syncing product {product_id} with logistics center...')

    product = Product.objects.get(id=product_id)

    logger.info('Syncing product data with logistics center')

    # make sure products (skus) are created
    if not add_or_update_product(product):
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

    message_body = json_body['DATACOLLECTION']['DATA']

    if message.message_type == LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name:
        handle_logistics_center_inbound_receipt_message(message, message_body)
    elif (
        message.message_type == LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name
    ):
        handle_logistics_center_order_status_change_message(message, message_body)
    elif message.message_type == LogisticsCenterMessageTypeEnum.SHIP_ORDER.name:
        handle_logistics_center_ship_order_message(message, message_body)
    else:
        raise Exception(f'Unknown message type: {message.message_type}')

    logger.info(f'Successfully processed logistics center message {message_id}!')


@shared_task
def sync_logistics_center_snapshots() -> bool:
    logger.info('Syncing with logistics center snapshots...')

    snapshot_count = 0

    # the only provider we currently support
    logistics_center = LogisticsCenterEnum.ORIAN.name

    for (
        snapshot_file_path,
        snapshot_date_time,
        snapshot_data,
    ) in fetch_logistics_center_snapshots():
        logger.info(f'Fetched snapshot {snapshot_file_path}, saving it...')

        storage = storages['logistics']
        storage_file_name = storage.generate_filename(
            os.path.join(
                logistics_center,
                snapshot_file_path,
            ),
        )

        # check if the snapshot is already in s3
        if storage.exists(storage_file_name):
            logger.info(f'Fetched snapshot {snapshot_file_path} is already saved')
            continue

        # otherwise put in s3
        buffer = BytesIO(snapshot_data)
        storage.save(storage_file_name, ContentFile(buffer.read()))
        logger.info(f'Fetched snapshot {snapshot_file_path} saved!')

        # call process task
        process_logistics_center_snapshot.apply_async(
            (logistics_center, snapshot_file_path, snapshot_date_time)
        )

        snapshot_count += 1

    logger.info(f'Successfully synced {snapshot_count} snapshot files!')


@shared_task
def process_logistics_center_snapshot(
    logistics_center: str, snapshot_file_path: str, snapshot_date_time: datetime
) -> bool:
    logger.info(
        f'Processing logistics center {logistics_center} snapshot '
        f'{snapshot_file_path}...'
    )

    storage = storages['logistics']
    storage_file_name = storage.generate_filename(
        os.path.join(
            logistics_center,
            snapshot_file_path,
        ),
    )

    # make sure the snapshot is already in s3
    if not storage.exists(storage_file_name):
        logger.error(
            f'Failed to process {logistics_center} snapshot '
            f'{snapshot_file_path} - file not found'
        )
        return False

    with storage.open(storage_file_name, 'r') as f:
        snapshot_data = f.read()

    snapshot_dict = xmltodict.parse(snapshot_data)

    # use transaction to make sure we have the entire snapshot in out db
    with transaction.atomic():
        # create stock snapshot record
        stock_snapshot_data = {
            'snapshot_file_path': snapshot_file_path,
            'processed_date_time': datetime.now(timezone.utc),
        }

        stock_snapshot, _ = LogisticsCenterStockSnapshot.objects.update_or_create(
            center=logistics_center,
            snapshot_date_time=snapshot_date_time,
            defaults=stock_snapshot_data,
            create_defaults=stock_snapshot_data,
        )

        # read snapshot lines list and convert value to list since with this
        # xml format if a single line was provided there is no way of knowing
        # it is part of an array
        snapshot_lines = snapshot_dict['DATACOLLECTION'].get('DATA', [])
        if not isinstance(snapshot_lines, list):
            snapshot_lines = [snapshot_lines]

        for snapshot_line in snapshot_lines:
            # create stock snapshot line record
            stock_snapshot_line_data = {'quantity': int(float(snapshot_line['QTY']))}

            LogisticsCenterStockSnapshotLine.objects.update_or_create(
                stock_snapshot=stock_snapshot,
                sku=snapshot_line['SKU'],
                defaults=stock_snapshot_line_data,
                create_defaults=stock_snapshot_line_data,
            )

    logger.info(
        f'Successfully processed logistics center {logistics_center} snapshot '
        f'{snapshot_file_path}!'
    )
    logger.info("Updating products' snapshot stock values...")

    # fetch the latest snapshot (the one we just processed may not be the
    # latest)
    latest_snapshot = LogisticsCenterStockSnapshot.objects.order_by(
        '-snapshot_date_time'
    )[0]
    latest_snapshot_lines = {line.sku: line for line in latest_snapshot.lines.all()}

    # new transaction for product updates
    with transaction.atomic():
        # update each product's logsitics snapshot stock
        for product in Product.objects.all():
            product.logistics_snapshot_stock_line = latest_snapshot_lines.get(
                product.sku, None
            )
            product.save(update_fields=['logistics_snapshot_stock_line'])

    logger.info("Successfully updated products' snapshot stock values!")

    return True


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
        'Supplier',
        'Brand',
        'SKU',
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
        'product_supplier',
        'product_brand',
        'product_sku',
        'product_reference',
        'total_ordered',
        'product_cost_price',
        'product_quantity',
        'in_transit_stock',
        'dc_stock',
        'difference_to_order',
    ):
        record = [
            order_summary['product_supplier'],
            order_summary['product_brand'],
            order_summary['product_sku'],
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
