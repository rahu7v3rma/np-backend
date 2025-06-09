from datetime import datetime, timezone
import json
import logging
from typing import Optional

from django.conf import settings
from django.db import transaction
import pytz
import requests

from campaign.models import (
    DeliveryLocationEnum,
    EmployeeGroupCampaign,
    Order,
    OrderProduct,
)
from inventory.models import Product

from ..enums import LogisticsCenterEnum
from ..models import (
    LogisticsCenterInboundReceipt,
    LogisticsCenterInboundReceiptLine,
    LogisticsCenterInboundStatus,
    LogisticsCenterMessage,
    LogisticsCenterOrderStatus,
    LogisticsCenterStockSnapshot,
    LogisticsCenterStockSnapshotLine,
    PurchaseOrder,
    PurchaseOrderProduct,
)


logger = logging.getLogger(__name__)


def add_or_update_inbound(
    purchase_order: PurchaseOrder, inbound_date_time: datetime
) -> bool:
    request_body = {
        'DATACOLLECTION': {
            'DATA': {
                'CONSIGNEE': settings.PAP_CONSIGNEE,
                'ORDERID': _platform_id_to_pap_id(purchase_order.pk),
                'ORDERTYPE': 'PO',  # our orders are always POs (purchase orders)
                # 'CONTAINER': '',
                # 'REFERENCEORD': '',
                'SOURCECOMPANY': remove_unsupported_chars(
                    purchase_order.supplier.name_he or purchase_order.supplier.name_en
                ),
                'COMPANYTYPE': 'VENDOR',  # suppliers are always VENDORs
                'CREATEDATE': inbound_date_time.strftime('%d-%m-%Y'),
                # 'EXPECTEDDATE': '',
                # 'ROUTE': '',
                # 'NOTES': '',
                'LINES': {
                    'LINE': [
                        {
                            'ORDERLINE': i,
                            'REFERENCEORDLINE': i,
                            'SKU': p.product_id.sku,
                            'QTYORDERED': p.quantity_ordered,
                            'INVENTORYSTATUS': 'AVAILABLE',  # always AVAILABLE
                            'SKUDESCRIPTION': remove_unsupported_chars(
                                p.product_id.name_he or p.product_id.name_en
                            ),
                            'MANUFACTURERSKU': p.product_id.reference,
                        }
                        for i, p in enumerate(purchase_order.products)
                    ]
                },
            }
        }
    }

    if settings.PAP_VERBOSE:
        logger.info(f'pap sending inbound payload: {json.dumps(request_body)}')

    response = requests.post(
        settings.PAP_INBOUND_URL,
        json=request_body,
    )

    if response.status_code != 200:
        logger.error(
            'pap failed to add or update inbound with status '
            f'{response.status_code} and response {response.text}'
        )
        return False

    # parse priority id and status from response and save it to the po
    try:
        response_json = response.json()
    except requests.exceptions.JSONDecodeError:
        logger.error(
            'pap failed to add or update inbound with non-json response: '
            f'"{response.text}"'
        )
        return False

    priority_po_id = response_json.get('PRIORITYPOID')
    priority_status = response_json.get('STATUS')
    purchase_order.logistics_center_id = priority_po_id
    purchase_order.logistics_center_status = priority_status
    purchase_order.logistics_center = LogisticsCenterEnum.PICK_AND_PACK.name
    purchase_order.save(
        update_fields=[
            'logistics_center_id',
            'logistics_center_status',
            'logistics_center',
        ],
    )

    logger.info(f'pap inbound added or updated with: {response.text}')
    return True


def add_or_update_outbound(
    order: Order, order_products: list[OrderProduct], outbound_date_time: datetime
) -> bool:
    # if the ordering employee's group is set to receive gifts at the office we
    # should use the office address and the office manager details for the
    # outbound delivery. otherwise use the address and checkout details the
    # user used when making the order
    employee = order.campaign_employee_id.employee
    employee_group = employee.employee_group
    if employee_group.delivery_location == DeliveryLocationEnum.ToOffice.name:
        outbound_delivery_street = remove_unsupported_chars(
            employee_group.delivery_street
        )
        outbound_delivery_street_number = remove_unsupported_chars(
            employee_group.delivery_street_number
        )
        outbound_delivery_apartment_number = remove_unsupported_chars(
            employee_group.delivery_apartment_number
        )
        outbound_delivery_city = remove_unsupported_chars(employee_group.delivery_city)
        outbound_delivery_additional_details = ''
        outbound_contact_1_name = remove_unsupported_chars(employee.full_name)
        outbound_contact_2_name = remove_unsupported_chars(
            employee_group.organization.manager_full_name
        )
        outbound_contact_1_phone_number = remove_unsupported_chars(
            employee.phone_number
        )
        outbound_contact_2_phone_number = remove_unsupported_chars(
            employee_group.organization.manager_phone_number
        )
        outbound_contact_1_email = remove_unsupported_chars(employee.email)
        outbound_contact_2_email = remove_unsupported_chars(
            employee_group.organization.manager_email
        )

        outbound_company_name = remove_unsupported_chars(
            employee_group.organization.name_he or employee_group.organization.name_en
        )

        # reference order field should group b2b orders (aka ones made to
        # offices)
        campaign_employee_group = EmployeeGroupCampaign.objects.get(
            employee_group=employee_group, campaign=order.campaign_employee_id.campaign
        )
        reference_order = _platform_id_to_pap_id(campaign_employee_group.pk)

        # for b2b orders nicklas will deliver
        route = 'CUSTOMER'
    else:
        outbound_delivery_street = remove_unsupported_chars(order.delivery_street)
        outbound_delivery_street_number = remove_unsupported_chars(
            order.delivery_street_number
        )
        outbound_delivery_apartment_number = remove_unsupported_chars(
            order.delivery_apartment_number
        )
        outbound_delivery_city = remove_unsupported_chars(order.delivery_city)
        outbound_delivery_additional_details = remove_unsupported_chars(
            order.delivery_additional_details
        )
        outbound_contact_1_name = remove_unsupported_chars(order.full_name)
        outbound_contact_2_name = remove_unsupported_chars(order.full_name)
        outbound_contact_1_phone_number = remove_unsupported_chars(order.phone_number)
        outbound_contact_2_phone_number = remove_unsupported_chars(
            order.additional_phone_number
        )
        outbound_contact_1_email = remove_unsupported_chars(employee.email)
        outbound_contact_2_email = ''

        outbound_company_name = ''

        reference_order = ''

        # for normal orders orian is the delivery value
        route = 'ORIAN'

    # build a list of bundle skus. multiple-quantity products should have their
    # skus displayed as many times as they were ordered
    bundle_skus = []
    for op in order.orderproduct_set.all():
        if op.product_id.product_id.product_kind == Product.ProductKindEnum.BUNDLE.name:
            for _ in range(op.quantity):
                bundle_skus.append(op.product_id.product_id.sku)

    bundle_skus_str = '|||'.join(bundle_skus)
    if len(bundle_skus_str) > 120:
        logger.warn(f'pap oubound bundle string too long: {bundle_skus_str}')
        bundle_skus_str = bundle_skus_str[:120]

    request_body = {
        'DATACOLLECTION': {
            'DATA': {
                'CONSIGNEE': settings.PAP_CONSIGNEE,
                'ORDERID': order.order_id,
                # our orders are always shipped to customers
                'ORDERTYPE': 'CUSTOMER',
                # reference order field should either have a value to group
                # b2b orders shipping to the same location together or no
                # value at all for orders shipping to employees' homes
                'REFERENCEORD': reference_order,
                # company name
                'COMPANYNAME': outbound_company_name,
                # outgoing is only sent to customer companies
                'COMPANYTYPE': 'CUSTOMER',
                'REQUESTEDDATE': outbound_date_time.strftime('%d-%m-%Y'),
                # 'SCHEDULEDDATE': '',
                'CREATEDATE': outbound_date_time.strftime('%d-%m-%Y'),
                'ROUTE': route,
                'NOTES': '',
                'SHIPPINGDETAIL': {
                    # 'CHECK1DATE': '',
                    # 'CHECK1AMOUNT': '',
                    # 'CHECK2DATE': '',
                    # 'CHECK2AMOUNT': '',
                    # 'CHECK3DATE': '',
                    # 'CHECK3AMOUNT': '',
                    # 'CASH': '',
                    # 'COLLECT': '',
                    # 'FRIDAY': '',
                    'DELIVERYCOMMENTS': outbound_delivery_additional_details,
                    # 'DELIVERYCONFIRMATION': '',
                    # 'FROMSCHEDUALEDELIVERYDATE': '',
                    # 'TOSCHEDUALEDELIVERYDATE': '',
                },
                'CONTACT': {
                    'STREET1': (
                        f'{outbound_delivery_street} {outbound_delivery_street_number}'
                    ),
                    'STREET2': f'דירה {outbound_delivery_apartment_number}'
                    if outbound_delivery_apartment_number
                    else '',
                    'CITY': outbound_delivery_city,
                    # 'STATE': '',
                    # 'ZIP': '',
                    'CONTACT1NAME': outbound_contact_1_name,
                    'CONTACT2NAME': outbound_contact_2_name,
                    'CONTACT1PHONE': outbound_contact_1_phone_number,
                    'CONTACT2PHONE': outbound_contact_2_phone_number,
                    # 'CONTACT1FAX': '',
                    # 'CONTACT2FAX': '',
                    'CONTACT1EMAIL': outbound_contact_1_email,
                    'CONTACT2EMAIL': outbound_contact_2_email,
                },
                'BUNDLE': bundle_skus_str,
                'LINES': {
                    'LINE': [
                        {
                            'ORDERLINE': i,
                            'REFERENCEORDLINE': i,
                            'SKU': p['sku'],
                            'QTYORIGINAL': p['quantity'],
                            # 'NOTES': '',
                            # 'BATCH': '',
                            # 'SERIAL': '',
                            'INVENTORYSTATUS': 'AVAILABLE',  # always AVAILABLE
                            'SKUDESCRIPTION': remove_unsupported_chars(
                                p['name_he'] or p['name_en']
                            ),
                            'MANUFACTURERSKU': p['reference'],
                        }
                        for i, p in enumerate(order_products)
                    ]
                },
            }
        }
    }

    if settings.PAP_VERBOSE:
        logger.info(f'pap sending outbound payload: {json.dumps(request_body)}')

    response = requests.post(
        settings.PAP_OUTBOUND_URL,
        json=request_body,
    )

    if response.status_code != 200:
        logger.error(
            'pap failed to add or update outbound with status '
            f'{response.status_code} and response {response.text}'
        )
        return False

    # parse priority id from response and save it to the order
    try:
        response_json = response.json()
    except requests.exceptions.JSONDecodeError:
        logger.error(
            'pap failed to add or update outbound with non-json response: '
            f'"{response.text}"'
        )
        return False

    priority_order_id = response_json.get('PRIORITY_ORDER_ID')
    order.logistics_center_id = priority_order_id
    order.logistics_center = LogisticsCenterEnum.PICK_AND_PACK.name
    order.save(update_fields=['logistics_center_id', 'logistics_center'])

    logger.info(f'outbound added or updated with: {response.text}')
    return True


def _platform_id_to_pap_id(platform_id: int) -> str:
    return f'NKS{settings.PAP_ID_PREFIX}{platform_id}'


def pap_id_to_platform_id(pap_id: str) -> int | None:
    try:
        return int(pap_id.removeprefix(f'NKS{settings.PAP_ID_PREFIX}'))
    except ValueError:
        return None


def handle_logistics_center_inbound_status_change_message(
    message: LogisticsCenterMessage, message_body: dict
):
    logistics_center_id = message_body['PRIORITYPOID']
    purchase_order_id = pap_id_to_platform_id(message_body['ORDERID'])
    purchase_order = PurchaseOrder.objects.get(id=purchase_order_id)

    status = message_body['STATUS']
    # pick and pack order status updates are immediate and apply to the time
    # the message was sent
    status_date_time = message.created_at

    _status_change, created = LogisticsCenterInboundStatus.objects.get_or_create(
        logistics_center_message=message,
        center=message.center,
        purchase_order=purchase_order,
        status=status,
        status_date_time=status_date_time,
    )

    # update the purchase order's logistics center status by querying for the
    # latest status update. the message being handled might not be the latest
    purchase_order.logistics_center_status = (
        LogisticsCenterInboundStatus.objects.filter(purchase_order=purchase_order)
        .order_by('-status_date_time')
        .first()
        .status
    )
    purchase_order.logistics_center_id = logistics_center_id
    purchase_order.save(
        update_fields=['logistics_center_status', 'logistics_center_id']
    )

    logger.info(
        f'Successfully processed pap logistics center inbound status change message '
        f'with {"created" if created else "updated"} status!'
    )


def handle_logistics_center_inbound_receipt_message(
    message: LogisticsCenterMessage, message_body: dict
):
    receipt_priority_po_id = message_body['PRIORITYPOID']

    receipt_data = {
        'receipt_start_date': datetime.strptime(
            message_body['STARTRECEIPTDATE'], '%m/%d/%Y %H:%M:%S %z'
        ),
        # with pick and pack receipt close date is determined by the status and
        # will just be empty
        'receipt_close_date': None,
        'status': message_body['STATUS'],
    }

    receipt, receipt_created = LogisticsCenterInboundReceipt.objects.update_or_create(
        center=message.center,
        receipt_code=message_body['RECEIPT'],
        defaults=receipt_data,
        create_defaults=receipt_data,
    )

    processed_created_lines = 0
    processed_updated_lines = 0

    for receipt_line in message_body['LINES']['LINE']:
        line_product_sku = receipt_line['SKU']

        line_purchase_order_product = PurchaseOrderProduct.objects.get(
            purchase_order__logistics_center_id=receipt_priority_po_id,
            product_id__sku=line_product_sku,
        )

        receipt_line_data = {
            'purchase_order_product': line_purchase_order_product,
            'quantity_received': int(float(receipt_line['QTYRECEIVED'])),
            'logistics_center_message': message,
        }
        _line, created = LogisticsCenterInboundReceiptLine.objects.update_or_create(
            receipt=receipt,
            receipt_line=int(receipt_line['RECEIPTLINE']),
            defaults=receipt_line_data,
            create_defaults=receipt_line_data,
        )

        if created:
            processed_created_lines += 1
        else:
            processed_updated_lines += 1

    logger.info(
        f'Successfully processed pap logistics center inbound receipt message '
        f'with {"created" if receipt_created else "updated"} receipt, '
        f'{processed_created_lines} created and {processed_updated_lines} '
        'updated receipt lines!'
    )


def handle_logistics_center_order_status_change_message(
    message: LogisticsCenterMessage, message_body: dict
):
    order = Order.objects.get(order_id=message_body['ORDERID'])

    status = message_body['STATUS']
    # pick and pack order status updates are immediate and apply to yhe time
    # the message was sent
    status_date_time = message.created_at

    _status_change, created = LogisticsCenterOrderStatus.objects.get_or_create(
        logistics_center_message=message,
        center=message.center,
        order=order,
        status=status,
        status_date_time=status_date_time,
    )

    # update the order's logistics center status by querying for the latest
    # status update. the message being handled might not be the latest
    order.logistics_center_status = (
        LogisticsCenterOrderStatus.objects.filter(order=order)
        .order_by('-status_date_time')
        .first()
        .status
    )
    order.save(update_fields=['logistics_center_status'])

    logger.info(
        f'Successfully processed pap logistics center order status change message '
        f'with {"created" if created else "updated"} status!'
    )


def handle_logistics_center_ship_order_message(
    message: LogisticsCenterMessage, message_body: dict
):
    order = Order.objects.get(order_id=message_body['ORDERID'])

    status = message_body.get('SHIPPING_STATUS')
    shipping_number = message_body['SHIPNU']

    if status:
        # pick and pack order status updates are immediate and apply to yhe time
        # the message was sent
        status_date_time = message.created_at

        _status_change, created = LogisticsCenterOrderStatus.objects.get_or_create(
            logistics_center_message=message,
            center=message.center,
            order=order,
            status=status,
            status_date_time=status_date_time,
        )
    else:
        created = False

    # update the order's logistics center status by querying for the latest
    # status update. the message being handled might not be the latest
    latest_order_status = (
        LogisticsCenterOrderStatus.objects.filter(order=order)
        .order_by('-status_date_time')
        .first()
    )

    if latest_order_status:
        order.logistics_center_status = latest_order_status.status
    order.logistics_center_shipping_number = shipping_number
    order.save(
        update_fields=['logistics_center_status', 'logistics_center_shipping_number']
    )

    logger.info(
        f'Successfully processed pap logistics center ship order message '
        f'with {"created" if created else "updated"} status!'
    )


def handle_logistics_center_snapshot_message(
    message: LogisticsCenterMessage, message_body: dict
):
    snapshot_date_time = datetime.strptime(
        message_body['snapshotDateTime'], '%m/%d/%Y %H:%M:%S'
    )
    # we need to localize the date time since we get no timezone info from pick
    # and pack, but it is a local time value
    snapshot_date_time = pytz.timezone(settings.PAP_MESSAGE_TIMEZONE_NAME).localize(
        snapshot_date_time
    )
    snapshot_lines = message_body['lines']

    # use transaction to make sure we have the entire snapshot in our db
    with transaction.atomic():
        # create stock snapshot record
        stock_snapshot_data = {
            'processed_date_time': datetime.now(timezone.utc),
        }

        stock_snapshot, stock_created = (
            LogisticsCenterStockSnapshot.objects.update_or_create(
                center=message.center,
                snapshot_date_time=snapshot_date_time,
                defaults=stock_snapshot_data,
                create_defaults=stock_snapshot_data,
            )
        )

        processed_created_lines = 0
        processed_updated_lines = 0

        # summarize snapshot lines since pick and pack send us the same sku
        # multiple times in a snapshot and we need to sum the quantities
        summarized_snapshot_lines = {}
        for snapshot_line in snapshot_lines:
            sku = snapshot_line['sku']
            quantity = int(float(snapshot_line['quantity']))

            if summarized_snapshot_lines.get(sku):
                summarized_snapshot_lines[sku] += quantity
            else:
                summarized_snapshot_lines[sku] = quantity

        for line_sku, line_quantity in summarized_snapshot_lines.items():
            # update or create stock snapshot line record
            stock_snapshot_line_data = {'quantity': line_quantity}

            _line, created = LogisticsCenterStockSnapshotLine.objects.update_or_create(
                stock_snapshot=stock_snapshot,
                sku=line_sku,
                defaults=stock_snapshot_line_data,
                create_defaults=stock_snapshot_line_data,
            )

            if created:
                processed_created_lines += 1
            else:
                processed_updated_lines += 1

    logger.info(
        f'Successfully processed pap logistics center snapshot message '
        f'with {"created" if stock_created else "updated"} stock, '
        f'{processed_created_lines} created and {processed_updated_lines} '
        'updated stock lines!'
    )

    logger.info('Updating product snapshot stock values...')

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

    logger.info('Successfully updated product snapshot stock values!')


def remove_unsupported_chars(original_value: Optional[str]) -> str:
    # pick and pack do not support quotes anywhere in values sent to them
    if original_value:
        return original_value.replace('"', '')
    else:
        return original_value
