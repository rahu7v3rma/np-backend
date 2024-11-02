from datetime import datetime
import logging
import time
from typing import Generator

from django.conf import settings
import paramiko
import requests

from campaign.models import (
    DeliveryLocationEnum,
    EmployeeGroupCampaign,
    Order,
    OrderProduct,
)
from inventory.models import Product, Supplier

from ..models import (
    LogisticsCenterInboundReceipt,
    LogisticsCenterInboundReceiptLine,
    LogisticsCenterMessage,
    LogisticsCenterOrderStatus,
    PurchaseOrder,
    PurchaseOrderProduct,
)


logger = logging.getLogger(__name__)


def _add_or_update_company(
    company_id: int,
    name: str,
    is_vendor: bool,
    address_street: str,
    address_street_number: str,
    address_city: str,
    phone_number: str,
) -> bool:
    request_body = {
        'DATACOLLECTION': {
            'DATA': {
                'CONSIGNEE': settings.ORIAN_CONSIGNEE,
                'COMPANYTYPE': 'VENDOR'
                if is_vendor
                else 'CUSTOMER',  # suppliers vendors, customers are customers
                'COMPANY': _platform_id_to_orian_id(company_id),
                'COMPANYNAME': name,
                # 'COMPANYGROUP': '',
                # 'OTHERCOMPANY': '',
                # 'STATUS': 1,
                # 'DELIVERYCOMMENTS': '',
                # 'DEFAULTCONTACT': '123',
                'CONTACTS': {
                    'CONTACT': [
                        {
                            # 'CONTACTID': 1234,
                            'STREET1': f'{address_street} {address_street_number}',
                            # 'STREET2': '',
                            'CITY': address_city,
                            # 'STATE': '',
                            # 'ZIP': '',
                            'CONTACT1NAME': name,
                            # 'CONTACT2NAME': '',
                            'CONTACT1PHONE': phone_number,
                            # 'CONTACT2PHONE': '',
                            # 'CONTACT1FAX': '',
                            # 'CONTACT2FAX': '',
                            # 'CONTACT1EMAIL': '',
                            # 'CONTACT2EMAIL': '',
                            # 'POINTID': '',
                            # 'ROUTE': '',
                            # 'STAGINGLANE': ''
                        }
                    ]
                },
            }
        }
    }

    response = requests.post(
        f'{settings.ORIAN_BASE_URL}/Company',
        # note that "bearer" must be all lower case
        headers={'Authorization': f'bearer {settings.ORIAN_API_TOKEN}'},
        json=request_body,
    )

    # note the success typo on responses from orian api
    if response.status_code != 200 or response.json()['status'] not in (
        'SUCCESS',
        'SUCCSESS',
    ):
        logger.error(
            'failed to add or update company with status '
            f'{response.status_code} and response {response.text}'
        )
        logger.error(f'request body was: {request_body}')
        return False

    logger.info(f'company added or updated with: {response.text}')
    return True


def add_or_update_supplier(supplier: Supplier) -> bool:
    result = _add_or_update_company(
        supplier.pk,
        supplier.name,
        True,
        supplier.address_street,
        supplier.address_street_number,
        supplier.address_city,
        supplier.phone_number,
    )

    return result


def add_or_update_dummy_customer() -> bool:
    # we create a dummy nicklas customer company and then add the address for
    # each outbound separately as per orian's instructions
    result = _add_or_update_company(
        settings.ORIAN_DUMMY_CUSTOMER_PLATFORM_ID,
        'Nicklas',
        False,
        settings.ORIAN_DUMMY_CUSTOMER_COMPANY_STREET,
        settings.ORIAN_DUMMY_CUSTOMER_COMPANY_STREET_NUMBER,
        settings.ORIAN_DUMMY_CUSTOMER_COMPANY_CITY,
        settings.ORIAN_DUMMY_CUSTOMER_COMPANY_PHONE_NUMBER,
    )

    return result


def add_or_update_product(product: Product) -> bool:
    product_name = product.name_he if product.name_he else product.name
    product_name = product_name.replace('"', '').replace("'", '').replace('`', '')

    response = requests.post(
        f'{settings.ORIAN_BASE_URL}/Sku',
        # note that "bearer" must be all lower case
        headers={'Authorization': f'bearer {settings.ORIAN_API_TOKEN}'},
        json={
            'DATACOLLECTION': {
                'DATA': {
                    'CONSIGNEE': settings.ORIAN_CONSIGNEE,
                    'SKU': product.sku,
                    'DEFAULTUOM': 'EACH',
                    'SKUDESCRIPTION': product_name[:255],
                    # 'PICKSORTORDER': '',
                    'SKUSHORTDESC': product_name[:150],
                    'MANUFACTURERSKU': product.reference,
                    'VENDORSKU': '',
                    'OTHERSKU': '',
                    # 'PICTURE': '',
                    # 'SKUGROUP': '',
                    # 'CLASSNAME': '',
                    'INITIALSTATUS': 'AVAILABLE',  # intial status is always AVAILABLE
                    # 'VELOCITY': '',
                    'NOTES': '',
                    # 'STORAGECLASS': '',
                    # 'HAZCLASS': '',
                    # 'PREFLOCATION': '',
                    # 'UNITPRICE': 0,
                    'UOMCOLLECTION': {
                        'UOMOBJ': [
                            {
                                'UOM': 'EACH',
                                # 'GROSSWEIGHT': 0.588,
                                # 'NETWEIGHT': 0,
                                # 'LENGTH': 7.1,
                                # 'WIDTH': 7.1,
                                # 'HEIGHT': 14.2,
                                # 'VOLUME': 715.822,
                                # 'LOWERUOM': 'EACH',
                                # 'UNITSPERMEASURE': 1
                            },
                        ],
                    },
                }
            }
        },
    )

    # note the success typo on responses from orian api
    if response.status_code != 200 or response.json()['status'] not in (
        'SUCCESS',
        'SUCCSESS',
    ):
        logger.error(
            'failed to add or update product with status '
            f'{response.status_code} and response {response.text}'
        )
        return False

    logger.info(f'product added or updated with: {response.text}')
    return True


def add_or_update_inbound(
    purchase_order: PurchaseOrder, inbound_date_time: datetime
) -> bool:
    response = requests.post(
        f'{settings.ORIAN_BASE_URL}/Inbound',
        # note that "bearer" must be all lower case
        headers={'Authorization': f'bearer {settings.ORIAN_API_TOKEN}'},
        json={
            'DATACOLLECTION': {
                'DATA': {
                    'CONSIGNEE': settings.ORIAN_CONSIGNEE,
                    'ORDERID': _platform_id_to_orian_id(purchase_order.pk),
                    'ORDERTYPE': 'PO',  # our orders are always POs (purchase orders)
                    # 'CONTAINER': '',
                    # 'REFERENCEORD': '',
                    'SOURCECOMPANY': _platform_id_to_orian_id(
                        purchase_order.supplier_id
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
                            }
                            for i, p in enumerate(purchase_order.products)
                        ]
                    },
                }
            }
        },
    )

    # note the success typo on responses from orian api
    if response.status_code != 200 or response.json()['status'] not in (
        'SUCCESS',
        'SUCCSESS',
    ):
        logger.error(
            'failed to add or update inbound with status '
            f'{response.status_code} and response {response.text}'
        )
        return False

    logger.info(f'inbound added or updated with: {response.text}')
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
        outbound_delivery_street = employee_group.delivery_street
        outbound_delivery_street_number = employee_group.delivery_street_number
        outbound_delivery_apartment_number = employee_group.delivery_apartment_number
        outbound_delivery_city = employee_group.delivery_city
        outbound_delivery_additional_details = ''
        outbound_contact_1_name = employee.full_name
        outbound_contact_2_name = employee_group.organization.manager_full_name
        outbound_contact_1_phone_number = employee.phone_number
        outbound_contact_2_phone_number = (
            employee_group.organization.manager_phone_number
        )
        outbound_contact_1_email = employee.email
        outbound_contact_2_email = employee_group.organization.manager_email

        # reference order field should group b2b orders (aka ones made to
        # offices)
        campaign_employee_group = EmployeeGroupCampaign.objects.get(
            employee_group=employee_group, campaign=order.campaign_employee_id.campaign
        )
        reference_order = _platform_id_to_orian_id(campaign_employee_group.pk)

        # for b2b orders nicklas will deliver
        route = 'CUSTOMER'
    else:
        outbound_delivery_street = order.delivery_street
        outbound_delivery_street_number = order.delivery_street_number
        outbound_delivery_apartment_number = order.delivery_apartment_number
        outbound_delivery_city = order.delivery_city
        outbound_delivery_additional_details = order.delivery_additional_details
        outbound_contact_1_name = order.full_name
        outbound_contact_2_name = order.full_name
        outbound_contact_1_phone_number = order.phone_number
        outbound_contact_2_phone_number = order.additional_phone_number
        outbound_contact_1_email = employee.email
        outbound_contact_2_email = ''

        reference_order = ''

        # for normal orders orian should deliver
        route = 'ORIAN'

    request_body = {
        'DATACOLLECTION': {
            'DATA': {
                'CONSIGNEE': settings.ORIAN_CONSIGNEE,
                'ORDERID': order.order_id,
                # our orders are always shipped to customers
                'ORDERTYPE': 'CUSTOMER',
                # reference order field should either have a value to group
                # b2b orders shipping to the same location together or no
                # value at all for orders shipping to employees' homes
                'REFERENCEORD': reference_order,
                'TARGETCOMPANY': _platform_id_to_orian_id(
                    settings.ORIAN_DUMMY_CUSTOMER_PLATFORM_ID
                ),  # our dummy customer company
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
                        f'{outbound_delivery_street} '
                        f'{outbound_delivery_street_number}'
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
                        }
                        for i, p in enumerate(order_products)
                    ]
                },
            }
        }
    }

    response = requests.post(
        f'{settings.ORIAN_BASE_URL}/Outbound',
        # note that "bearer" must be all lower case
        headers={'Authorization': f'bearer {settings.ORIAN_API_TOKEN}'},
        json=request_body,
    )

    # note the success typo on responses from orian api
    if response.status_code != 200 or response.json()['status'] not in (
        'SUCCESS',
        'SUCCSESS',
    ):
        logger.error(
            'failed to add or update outbound with status '
            f'{response.status_code} and response {response.text}'
        )
        logger.error(f'request body was: {request_body}')
        return False

    logger.info(f'outbound added or updated with: {response.text}')
    return True


def _platform_id_to_orian_id(platform_id: int) -> str:
    return f'NKS{settings.ORIAN_ID_PREFIX}{platform_id}'


def orian_id_to_platform_id(orian_id: str) -> int | None:
    try:
        return int(orian_id.removeprefix(f'NKS{settings.ORIAN_ID_PREFIX}'))
    except ValueError:
        return None


def handle_logistics_center_inbound_receipt_message(
    message: LogisticsCenterMessage, message_body: dict
):
    receipt_data = {
        'receipt_start_date': datetime.strptime(
            message_body['STARTRECEIPTDATE'], '%m/%d/%Y %I:%M:%S %p'
        ),
        'receipt_close_date': datetime.strptime(
            message_body['CLOSERECEIPTDATE'], '%m/%d/%Y %I:%M:%S %p'
        ),
    }

    receipt, receipt_created = LogisticsCenterInboundReceipt.objects.update_or_create(
        center=message.center,
        receipt_code=message_body['RECEIPT'],
        defaults=receipt_data,
        create_defaults=receipt_data,
    )

    processed_created_lines = 0
    processed_updated_lines = 0

    # format lines - if there is only one line the LINE object is just a dict
    # of that line, but if there are mroe the LINE object is a list of line
    # dicts
    receipt_lines_raw = message_body['LINES']['LINE']
    receipt_lines = (
        receipt_lines_raw
        if isinstance(receipt_lines_raw, list)
        else [receipt_lines_raw]
    )

    for receipt_line in receipt_lines:
        line_purchase_order_id = orian_id_to_platform_id(receipt_line['ORDERID'])
        line_product_sku = receipt_line['SKU']

        line_purchase_order_product = PurchaseOrderProduct.objects.get(
            purchase_order_id=line_purchase_order_id,
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
        f'Successfully processed logistics center inbound receipt message '
        f'with {"created" if receipt_created else "updated"} receipt, '
        f'{processed_created_lines} created and {processed_updated_lines} '
        'updated receipt lines!'
    )


def handle_logistics_center_order_status_change_message(
    message: LogisticsCenterMessage, message_body: dict
):
    try:
        order = Order.objects.get(order_id=message_body['ORDERID'])
    except Order.DoesNotExist:
        # try parsing the deprecated order id format. this can be removed in
        # the future when we don't have any old orders pending updates
        order_id = orian_id_to_platform_id(message_body['ORDERID'])
        order = Order.objects.get(pk=order_id)

    status = message_body['TOSTATUS']
    status_date_time = datetime.strptime(
        message_body['STATUSDATE'], '%m/%d/%Y %I:%M:%S %p'
    )

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
        f'Successfully processed logistics center order status change message '
        f'with {"created" if created else "updated"} status!'
    )


def handle_logistics_center_ship_order_message(
    message: LogisticsCenterMessage, message_body: dict
):
    try:
        order = Order.objects.get(order_id=message_body['ORDERID'])
    except Order.DoesNotExist:
        # try parsing the deprecated order id format. this can be removed in
        # the future when we don't have any old orders pending updates
        order_id = orian_id_to_platform_id(message_body['ORDERID'])
        order = Order.objects.get(pk=order_id)

    status = message_body['STATUS']  # should be "SHIPPED"
    status_date_time = datetime.strptime(
        message_body['SHIPPEDDATE'], '%m/%d/%Y %I:%M:%S %p'
    )

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
        f'Successfully processed logistics center ship order message '
        f'with {"created" if created else "updated"} status!'
    )


def fetch_logistics_center_snapshots() -> (
    Generator[tuple[str, datetime, bytes], None, None]
):
    """
    This generator connects to Orian's SFTP server, downloads snapshots and
    yields the relevant ones
    """
    transport = paramiko.Transport((settings.ORIAN_SFTP_HOST, settings.ORIAN_SFTP_PORT))

    try:
        transport.connect(
            None,
            settings.ORIAN_SFTP_USER,
            settings.ORIAN_SFTP_PASSWORD,
        )
        sftp = paramiko.SFTPClient.from_transport(transport)

        snapshot_files = sftp.listdir(settings.ORIAN_SFTP_SNAPSHOTS_DIR)

        for snapshot_file in snapshot_files:
            snapshot_path = f'{settings.ORIAN_SFTP_SNAPSHOTS_DIR}/{snapshot_file}'

            snapshot_modified_time_epoch_seconds = sftp.stat(snapshot_path).st_mtime
            max_snapshot_file_age_seconds = 60 * 60 * 24 * 7  # 1 week

            # make sure snapshot is not too old
            if (
                int(time.time()) - snapshot_modified_time_epoch_seconds
                < max_snapshot_file_age_seconds
            ):
                with sftp.open(snapshot_path, 'r') as f:
                    snapshot_data = f.read()

                # parse snapshot's date-time from its file name
                snapshot_date_time = datetime.strptime(
                    snapshot_file.split('_')[2], '%d%m%Y%H%M'
                )

                yield (snapshot_file, snapshot_date_time, snapshot_data)
    finally:
        try:
            transport.close()
        except Exception as _:
            pass
