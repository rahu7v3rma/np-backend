from datetime import datetime
import logging

from celery import shared_task

from payment.models import PaymentInformation
from payment.utils import approve_transaction
from services.email import send_order_confirmation_email


logger = logging.getLogger(__name__)


@shared_task
def process_payment(payload_data: dict[str, str]) -> bool:
    process_id = payload_data['data[processId]']
    logger.info(f'processing payment of process {process_id}...')

    existing_payment = PaymentInformation.objects.filter(process_id=process_id).first()

    if not existing_payment:
        logger.info(f'could not find existing payment of process {process_id}')
    elif existing_payment.is_paid:
        logger.info(f'existing payment of process {process_id} was already paid')
    else:
        logger.info(
            f'existing payment of process {process_id} found, checking if it '
            'was paid...'
        )
        employee_order = existing_payment.order

        # check if the order payment was completed yet
        was_paid = payload_data['data[statusCode]'] == '2'

        # if so, update the payment information object, approve the transaction
        # and update the order
        if was_paid:
            logger.info(f'existing payment of process {process_id} was paid!')

            # approve the transaction by reflecting back all its data to grow
            approval_result = approve_transaction(
                payload_data['data[transactionId]'],
                payload_data['data[transactionToken]'],
                payload_data['data[transactionTypeId]'],
                payload_data['data[paymentType]'],
                payload_data['data[sum]'],
                payload_data['data[firstPaymentSum]'],
                payload_data['data[periodicalPaymentSum]'],
                payload_data['data[paymentsNum]'],
                payload_data['data[allPaymentsNum]'],
                payload_data['data[paymentDate]'],
                payload_data['data[asmachta]'],
                payload_data['data[description]'],
                payload_data['data[fullName]'],
                payload_data['data[payerPhone]'],
                payload_data['data[payerEmail]'],
                payload_data['data[cardSuffix]'],
                payload_data['data[cardType]'],
                payload_data['data[cardTypeCode]'],
                payload_data['data[cardBrand]'],
                payload_data['data[cardBrandCode]'],
                payload_data['data[cardExp]'],
                payload_data['data[processId]'],
                payload_data['data[processToken]'],
            )

            if approval_result:
                # update payment information object
                existing_payment.payment_date = datetime.strptime(
                    payload_data['data[paymentDate]'], '%d/%m/%y'
                )
                existing_payment.transaction_id = payload_data['data[transactionId]']
                existing_payment.transaction_token = payload_data[
                    'data[transactionToken]'
                ]
                existing_payment.asmachta = payload_data['data[asmachta]']
                existing_payment.is_paid = True
                existing_payment.save(
                    update_fields=[
                        'payment_date',
                        'transaction_id',
                        'transaction_token',
                        'asmachta',
                        'is_paid',
                    ]
                )

                # update order status
                employee_order.status = employee_order.OrderStatusEnum.PENDING.name
                employee_order.save(update_fields=['status'])

                # send order confirmation email to employee
                send_order_confirmation_email(employee_order)
            else:
                logger.info(f'payment approval failed for process {process_id}')
        else:
            logger.info(f'existing payment of process {process_id} was not paid yet')

    logger.info(f'done validating payment of process {process_id}')
