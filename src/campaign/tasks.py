from datetime import datetime, timezone
from io import BytesIO
import logging
import os
from typing import Literal
import uuid

from celery import shared_task
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db.models.sql.query import Query
from openpyxl import Workbook

from inventory.utils import fill_message_template_email, fill_message_template_sms
from services.email import (
    send_campaign_welcome_email,
    send_export_download_email,
)
from services.sms import send_campaign_welcome_sms

from .models import (
    Campaign,
    Employee,
    EmployeeGroupCampaign,
    Order,
    OrganizationProduct,
)
from .serializers import OrderExportSerializer


logger = logging.getLogger(__name__)


@shared_task
def send_campaign_welcome_messages(campaign_id: int, employee_ids=None) -> bool:
    logger.info(f'sending welcome messages for campaign {campaign_id}...')

    campaign = Campaign.objects.filter(id=campaign_id).first()

    if not campaign:
        logger.warn(f'campaign {campaign_id} not found for welcome messages')
        return False

    for employee_group_campaign in campaign.employeegroupcampaign_set.all():
        logger.info(
            'sending welcome messages to campaign employee group '
            f'{employee_group_campaign.id}...'
        )
        sent_count = 0

        for employee in employee_group_campaign.employee_group.employee_set.all():
            # If employee_ids is provided and the current employee is not in the list,
            # skip sending the invitation
            if employee_ids and employee.id not in employee_ids:
                continue

            if employee_group_campaign.employee_group.auth_method == 'EMAIL':
                send_campaign_welcome_message_email.apply_async(
                    (employee.id, employee_group_campaign.id, campaign_id)
                )
                sent_count += 1
            elif employee_group_campaign.employee_group.auth_method == 'SMS':
                send_campaign_welcome_message_sms.apply_async(
                    (employee.id, employee_group_campaign.id, campaign_id)
                )
                sent_count += 1

        logger.info(
            f'sent welcome messages to {sent_count} employees in campaign '
            f'employee group {employee_group_campaign.id}'
        )

    logger.info(f'done sending welcome messages for campaign {campaign_id}')


@shared_task
def send_campaign_welcome_message_email(
    employee_id: int, employee_group_campaign_id: int, campaign_id: int
):
    employee = Employee.objects.filter(id=employee_id, active=True).first()
    employee_group_campaign = EmployeeGroupCampaign.objects.filter(
        id=employee_group_campaign_id
    ).first()
    campaign = Campaign.objects.filter(id=campaign_id).first()

    if not employee or not employee_group_campaign or not campaign:
        logger.error(
            f'send_campaign_welcome_message_email could not find active '
            f'employee {employee_id} and campaign {campaign_id}'
        )
        raise Exception('employee or campaign not found')

    if not employee.email:
        logger.error(
            f'send_campaign_welcome_message_email employee {employee_id} has '
            'no email address'
        )
        raise Exception('employee has no email address')

    email_welcome_text = fill_message_template_email(
        employee=employee, campaign=campaign
    )

    if employee.default_language == 'HE':
        subject = f'הוזמנת לבחור מתנות של {campaign.name_he}!'
    else:
        subject = f'You are invited to pick your gifts for {campaign.name_en}!'

    body = email_welcome_text

    link_url = employee.get_campaign_site_link(campaign.code)

    send_campaign_welcome_email(employee.email, subject, body, link_url)


@shared_task
def send_campaign_welcome_message_sms(
    employee_id: int, employee_group_campaign_id: int, campaign_id: int
):
    employee = Employee.objects.filter(id=employee_id, active=True).first()
    employee_group_campaign = EmployeeGroupCampaign.objects.filter(
        id=employee_group_campaign_id
    ).first()
    campaign = Campaign.objects.filter(id=campaign_id).first()

    if not employee or not employee_group_campaign or not campaign:
        logger.error(
            f'send_campaign_welcome_message_sms could not find active '
            f'employee {employee_id} and campaign {campaign_id}'
        )
        raise Exception('employee or campaign not found')

    if not employee.phone_number:
        logger.error(
            f'send_campaign_welcome_message_sms employee {employee_id} has no '
            'phoner number'
        )
        raise Exception('employee has no phone number')

    message_text = fill_message_template_sms(employee=employee, campaign=campaign)

    send_campaign_welcome_sms(
        campaign.sms_sender_name, employee.phone_number, message_text
    )


# must use pickle task serializer for the query argument
@shared_task(serializer='pickle')
def export_orders_as_xlsx(
    orders_query: Query,
    exporter_user_id: int,
    exporter_email: str,
    base_export_download_url: str,
) -> bool:
    """
    Export all queried orders as an xlsx file. This method retuns a
    HttpResponse which can be returned as-is by actions
    """

    export_init_datetime = datetime.now(timezone.utc)

    # restoring the Order model queryset as described in the docs -
    # https://docs.djangoproject.com/en/5.1/ref/models/querysets/#pickling-querysets
    orders_queryset = Order.objects.all()
    orders_queryset.query = orders_query

    field_names = [
        'order id',
        'reference',
        'campaign name',
        'campaign active',
        'employee name',
        'employee email',
        'employee group',
        'phone number',
        'additional phone number',
        'organization name',
        'product name',
        'sku',
        'supplier name',
        'brand name',
        'quantity',
        'cost price',
        'logistics rate',
        'total cost',
        'order date time',
        'delivery street',
        'delivery street number',
        'delivery apartment number',
        'delivery city',
        'delivery country',
        'delivery state code',
        'delivery zip code',
        'delivery additional details',
        'product type',
        'product kind',
        'organization price',
        'status',
        'DC status',
        'Last Status Change',
    ]

    workbook = Workbook()
    worksheet = workbook.active

    all_variation_keys = set()

    for order in (
        orders_queryset.select_related('campaign_employee_id')
        .prefetch_related(
            'campaign_employee_id__campaign',
            'campaign_employee_id__campaign__organization',
            'campaign_employee_id__employee',
            'campaign_employee_id__employee__employee_group',
        )
        .all()
    ):
        for order_product in order.ordered_products():
            variations = order_product.get('variations')
            if variations:
                all_variation_keys.update(variations.keys())

    sorted_variation_keys = sorted(all_variation_keys)

    for key in sorted_variation_keys:
        field_names.insert(field_names.index('sku'), key)

    worksheet.append(field_names)

    for order in (
        orders_queryset.select_related('campaign_employee_id')
        .prefetch_related(
            'campaign_employee_id__campaign',
            'campaign_employee_id__campaign__organization',
            'campaign_employee_id__employee',
            'campaign_employee_id__employee__employee_group',
        )
        .all()
    ):
        order_serializer = OrderExportSerializer(order).data
        for order_product in order.ordered_products():
            record = []
            record.append(order.order_id)
            record.append(order_serializer.get('reference'))
            record.append(order_serializer.get('campaign', {}).get('name', ''))
            record.append(order_serializer.get('campaign', {}).get('is_active', ''))
            record.append(order_serializer.get('employee', {}).get('full_name'))
            record.append(order_serializer.get('employee', {}).get('email', '') or '')
            record.append(order_serializer.get('employee_group', {}).get('name'))
            record.append(order_serializer.get('phone_number'))
            record.append(order_serializer.get('additional_phone_number'))
            record.append(order.organization())
            record.append(order_product.get('name'))

            variations = order_product.get('variations', {})
            if variations:
                for key in sorted_variation_keys:
                    record.append(variations.get(key, None))
            else:
                record.extend([None] * len(sorted_variation_keys))

            record.append(order_product.get('sku'))
            record.append(order_product.get('supplier').get('name'))
            record.append(order_product.get('brand').get('name'))
            record.append(order_product.get('quantity'))
            record.append(order_product.get('cost_price'))
            record.append(order_product.get('logistics_rate_cost_percent'))
            record.append(order_product.get('total_cost'))
            record.append(order_serializer.get('order_date_time'))
            record.append(order_serializer.get('delivery_street'))
            record.append(order_serializer.get('delivery_street_number'))
            record.append(order_serializer.get('delivery_apartment_number'))
            record.append(order_serializer.get('delivery_city'))
            record.append(order_serializer.get('country'))
            record.append(order_serializer.get('state_code'))
            record.append(order_serializer.get('zip_code'))
            record.append(order_serializer.get('delivery_additional_details'))
            record.append(order_product.get('product_type'))
            record.append(order_product.get('product_kind'))
            record.append(
                getattr(
                    OrganizationProduct.objects.filter(
                        product=order_product.get('id'),
                        organization=order_serializer.get('organization'),
                    ).first(),
                    'price',
                    order_product.get('sale_price'),
                )
            )
            record.append(order_serializer.get('status'))
            record.append(order_serializer.get('logistics_center_status'))
            record.append(order_serializer.get('dc_status_last_changed'))

            worksheet.append(record)

    storage = storages['exports']

    formatted_init_datetime = export_init_datetime.strftime('%Y_%m_%d_%H%M')
    export_file_name = storage.generate_filename(
        os.path.join(
            str(uuid.uuid4()),
            f'orders_export_{formatted_init_datetime}.xlsx',
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
        'order', exporter_email, f'{base_export_download_url}{export_file_name}'
    )

    return True


@shared_task
def send_campaign_employee_invitation(
    campaign_id: int,
    employee_ids=None,
    invitation_type: list[Literal['email', 'sms']] = [],
):
    logger.info(
        f'sending campaign id:{campaign_id} invitation to {len(employee_ids)} employees'  # noqa: E501
    )

    campaign = Campaign.objects.filter(id=campaign_id).first()

    if not campaign:
        logger.warn(f'campaign id: {campaign_id} not found for employee invitations')
        return

    employees = Employee.objects.filter(id__in=employee_ids)
    sent_count = 0
    for employee in employees:
        logger.info(f'sending invitation message to employee id: {employee.id}')

        if employee.email and 'email' in invitation_type:
            welcome_message = fill_message_template_email(
                employee=employee, campaign=campaign
            )
            send_campaign_welcome_email(
                employee.email,
                "You're Invited!",
                welcome_message,
                employee.get_campaign_site_link(campaign.code),
            )
            sent_count += 1

        if employee.phone_number and 'sms' in invitation_type:
            welcome_message = fill_message_template_sms(
                employee=employee, campaign=campaign
            )
            send_campaign_welcome_sms(
                campaign.sms_sender_name,
                employee.phone_number,
                welcome_message,
            )
            sent_count += 1

        logger.info(
            f'campaign invitation sent to {sent_count} out of {len(employee_ids)} employees'  # noqa: E501
        )

    logger.info(
        f'done sending campaign id: {campaign_id} invitation to {len(employee_ids)} employees'  # noqa: E501
    )
