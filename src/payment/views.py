import json
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from payment.tasks import process_payment


logger = logging.getLogger(__name__)


class PaymentWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    # grow's webhook payload is sent as form data
    parser_classes = [FormParser]

    def post(self, request):
        try:
            payload_data = request.data

            logger.info(f'Payment webhook payload received: {json.dumps(payload_data)}')

            if (
                payload_data['data[customFields][cField1]']
                == settings.GROW_WEBHOOK_SECRET
            ):
                process_payment.apply_async((payload_data,))
            else:
                logger.error(
                    'Webhook payload failed secret validation for payload: '
                    f'{json.dumps(payload_data)}'
                )
        except Exception as ex:
            logger.info(
                f'An error has occurred while processing the webhook payload: {ex}'
            )

        return Response(
            {
                'success': True,
                'status': status.HTTP_200_OK,
                'data': {},
            },
            status=status.HTTP_200_OK,
        )
