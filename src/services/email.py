import logging
import os
from typing import Optional, Union

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template

from campaign.models import Order
from logistics.models import PurchaseOrder


logger = logging.getLogger(__name__)


def send_mail(
    send_to: list,
    subject: str,
    message: Optional[str] = None,
    from_email: Optional[str] = settings.DEFAULT_FROM_EMAIL,
    reply_to: Optional[list[str]] = None,
    context: Optional[dict] = None,
    cc_emails: Optional[list[str]] = None,
    bcc_emails: Optional[list[str]] = None,
    attachments: Optional[list[Union[Optional[dict]]]] = None,
    plaintext_email_template: Optional[Union[str, bytes, os.PathLike]] = None,
    html_email_template: Optional[Union[str, bytes, os.PathLike]] = None,
    fail_silently: Optional[bool] = False,
) -> bool:
    if reply_to is None:
        reply_to = [settings.REPLY_TO_EMAIL]
    if attachments is None:
        attachments = []
    if context is None:
        context = {}
    if cc_emails is None:
        cc_emails = []
    if bcc_emails is None:
        bcc_emails = []

    if plaintext_email_template:
        text_content = get_template(plaintext_email_template).render(context)
    else:
        text_content = message

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email,
        to=send_to,
        cc=cc_emails,
        bcc=bcc_emails,
        reply_to=reply_to,
    )

    if html_email_template:
        html_content = get_template(html_email_template).render(context)
        msg.attach_alternative(html_content, 'text/html')
        msg.content_subtype = 'html'

    for attachment in attachments:
        msg.attach(
            attachment['filename'],
            attachment['content'],
            attachment['mimetype'],
        )

    try:
        msg.send(fail_silently=fail_silently)
        return True
    except Exception as error:
        message = f'Failed sending email [{subject}] to {send_to} error: {error}'
        logger.error(
            message,
            exc_info=True,
            extra={
                'email': message,
                'error': error,
            },
        )
        return False


def send_reset_password_email(email: str, reset_password_link: str):
    context = {'reset_password_link': reset_password_link}
    res = send_mail(
        [email],
        'Reset your password',
        context=context,
        plaintext_email_template='emails/reset_password.txt',
        html_email_template='emails/reset_password.html',
    )
    return res


def send_otp_token_email(email: str, otp_token: str):
    context = {'otp_token': otp_token}
    res = send_mail(
        [email],
        'Your OTP Token',
        context=context,
        plaintext_email_template='emails/otp_token.txt',
        html_email_template='emails/otp_token.html',
    )
    return res


def send_campaign_welcome_email(email: str, subject: str, body: str, link_url: str):
    context = {
        'subject': subject,
        'body': body,
        'link_url': link_url,
    }
    res = send_mail(
        [email],
        subject,
        context=context,
        plaintext_email_template='emails/campaign_welcome.txt',
        html_email_template='emails/campaign_welcome.html',
    )
    return res


def send_order_confirmation_email(order: Order):
    subject = f'Order Confirmation #{order.reference}'
    customer_email = order.campaign_employee_id.employee.email
    context = {'order': order}

    res = send_mail(
        [customer_email],
        subject,
        context=context,
        plaintext_email_template='emails/order_confirmation_email.txt',
        html_email_template='emails/order_confirmation_email.html',
    )
    return res


def send_export_download_email(
    export_object_name: str, exporter_email: str, download_url: str
) -> bool:
    subject = f'Your {export_object_name} export is ready!'
    context = {
        'subject': subject,
        'export_object_name': export_object_name,
        'download_url': download_url,
    }

    res = send_mail(
        [exporter_email],
        subject,
        context=context,
        plaintext_email_template='emails/export_download_email.txt',
        html_email_template='emails/export_download_email.html',
    )
    return res


def send_purchase_order_email(purchase_order: PurchaseOrder):
    subject = f'Purchase Order #{purchase_order.id}'
    email = purchase_order.supplier.email
    product_name = purchase_order.products.all().values_list(
        'product_id__name', flat=True
    )
    product_sku = purchase_order.products.all().values_list(
        'product_id__sku', flat=True
    )
    quantity_order = purchase_order.products.all().values_list(
        'quantity_ordered', flat=True
    )
    context = {
        'po': purchase_order,
        'product_name': product_name,
        'product_sku': product_sku,
        'quantity_order': quantity_order,
    }

    res = send_mail(
        [email],
        subject,
        context=context,
        plaintext_email_template='emails/purchase_order.txt',
        html_email_template='emails/purchase_order.html',
    )
    return res
