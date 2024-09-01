import json
import logging

from django.conf import settings
import requests

from campaign.models import Order

from .models import PaymentInformation


logger = logging.getLogger(__name__)


def initiate_payment(
    order: Order,
    amount: int,
    payer_full_name: str | None,
    payer_phone_number: str | None,
    products_payment: dict[str:str],
    invoice_name: str,
    lang: str,
    description: str,
) -> str | None:
    base_redirect_url = (
        f'{settings.EMPLOYEE_SITE_BASE_URL}/{order.campaign_employee_id.campaign.code}'
    )

    # products payment is not sent with the request any longer since it turns
    # out that in prod grow require prices with each product details and verify
    # that the prices all add up to the payment sum
    payload = {
        'pageCode': settings.GROW_PAGE_CODE,
        'userId': settings.GROW_USER_ID,
        'apiKey': settings.GROW_API_KEY,
        'sum': amount,
        'description': description,
        'pageField[invoiceName]': invoice_name,
        'successUrl': f'{base_redirect_url}/order',
        'cancelUrl': f'{base_redirect_url}/checkout',
        # this is a custom field, we use it to validate that grow is the
        # ones talking to us via the webhook
        'cField1': settings.GROW_WEBHOOK_SECRET,
    }

    if payer_full_name and payer_phone_number:
        payload['pageField[fullName]'] = payer_full_name
        payload['pageField[phone]'] = payer_phone_number

    response = requests.post(
        f'{settings.GROW_BASE_URL}/createPaymentProcess', data=payload
    )
    response_json = response.json()

    if response_json.get('status') != 1:
        logger.error(
            f'initiate_payment failed to create payment process with '
            f'status {response.status_code} and body {response.text}'
        )
        return None

    payment_data = response_json.get('data', None)

    payment_information = PaymentInformation.objects.create(
        order=order,
        process_token=payment_data['processToken'],
        process_id=payment_data['processId'],
        amount=amount,
    )

    payment_information.save()

    return payment_data['authCode']


# def check_payment_finalized(order: Order) -> bool:
#     payment_information = PaymentInformation.objects.filter(
#         order=order, is_paid=False
#     ).first()

#     if not payment_information:
#         logger.error(
#             f'check_payment_finalized could not find unpaid payment '
#             f'information for order reference {order.reference}'
#         )
#         return False

#     payload = {
#         'pageCode': settings.GROW_PAGE_CODE,
#         'userId': settings.GROW_USER_ID,
#         'apiKey': settings.GROW_API_KEY,
#         'processId': payment_information.process_id,
#         'processToken': payment_information.process_token,
#     }

#     response = requests.post(
#         f'{settings.GROW_BASE_URL}/getPaymentProcessInfo', data=payload
#     )
#     response_json = response.json()

#     if response_json.get('status') != 1:
#         logger.error(
#             f'check_payment_finalized failed to get payment process info with '
#             f'status {response.status_code} and body {response.text}'
#         )
#         return False

#     logger.info(
#         f'Payment process info for process id {payment_information.process_id}'
#         f': {json.dumps(response.json())}'
#     )

#     payment_data = response_json.get('data', None)

#     for transaction in payment_data['transactions']:
#         # "2" is the code for "paid" status
#         if transaction['statusCode'] == '2':
#             payment_information.payment_date = datetime.strptime(
#                 transaction['paymentDate'], '%d/%m/%y'
#             )
#             payment_information.transaction_id = transaction['transactionId']
#             payment_information.transaction_token = transaction['transactionToken']
#             payment_information.asmachta = transaction['asmachta']
#             payment_information.is_paid = True
#             payment_information.save(
#                 update_fields=[
#                     'payment_date',
#                     'transaction_id',
#                     'transaction_token',
#                     'asmachta',
#                     'is_paid',
#                 ]
#             )

#             # approve the transaction by reflecting back all its data to grow
#             approve_transaction(
#                 transaction['transactionId'],
#                 transaction['transactionToken'],
#                 transaction['transactionTypeId'],
#                 transaction['paymentType'],
#                 transaction['sum'],
#                 transaction['firstPaymentSum'],
#                 transaction['periodicalPaymentSum'],
#                 transaction['paymentsNum'],
#                 transaction['allPaymentsNum'],
#                 transaction['paymentDate'],
#                 transaction['asmachta'],
#                 transaction['description'],
#                 transaction['fullName'],
#                 transaction['payerPhone'],
#                 transaction['payerEmail'],
#                 transaction['cardSuffix'],
#                 transaction['cardType'],
#                 transaction['cardTypeCode'],
#                 transaction['cardBrand'],
#                 transaction['cardBrandCode'],
#                 transaction['cardExp'],
#                 payment_data['processId'],
#                 payment_data['processToken'],
#             )

#             return True

#     # payment process was not paid yet
#     return False


def approve_transaction(
    transaction_id: str,
    transaction_token: str,
    transaction_type_id: str,
    payment_type: str,
    payment_sum: str,
    first_payment_sum: str,
    periodical_payment_sum: str,
    payments_num: str,
    all_payments_num: str,
    payment_date: str,
    asmachta: str,
    description: str,
    full_name: str,
    payer_phone: str,
    payer_email: str,
    card_suffix: str,
    card_type: str,
    card_type_code: str,
    card_brand: str,
    card_brand_code: str,
    card_exp: str,
    process_id: str,
    process_token: str,
) -> bool:
    payload = {
        'pageCode': settings.GROW_PAGE_CODE,
        'userId': settings.GROW_USER_ID,
        'apiKey': settings.GROW_API_KEY,
        'transactionId': transaction_id,
        'transactionToken': transaction_token,
        'transactionTypeId': transaction_type_id,
        'paymentType': payment_type,
        'sum': payment_sum,
        'firstPaymentSum': first_payment_sum,
        'periodicalPaymentSum': periodical_payment_sum,
        'paymentsNum': payments_num,
        'allPaymentsNum': all_payments_num,
        'paymentDate': payment_date,
        'asmachta': asmachta,
        'description': description,
        'fullName': full_name,
        'payerPhone': payer_phone,
        'payerEmail': payer_email,
        'cardSuffix': card_suffix,
        'cardType': card_type,
        'cardTypeCode': card_type_code,
        'cardBrand': card_brand,
        'cardBrandCode': card_brand_code,
        'cardExp': card_exp,
        'processId': process_id,
        'processToken': process_token,
    }

    response = requests.post(
        f'{settings.GROW_BASE_URL}/approveTransaction', data=payload
    )
    response_json = response.json()

    if response_json.get('status') != 1:
        logger.error(
            f'approve_transaction failed to approve transaction with '
            f'status {response.status_code} and body {response.text}'
        )
        return False

    logger.info(f'Payment approval response: {json.dumps(response_json)}')
    return True
