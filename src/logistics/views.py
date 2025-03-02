import json
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import IsCorrectProvider, ProviderAuthentication
from .enums import LogisticsCenterEnum, LogisticsCenterMessageTypeEnum
from .models import LogisticsCenterMessage
from .tasks import process_logistics_center_message


logger = logging.getLogger(__name__)


class ProviderWebhookView(APIView):
    authentication_classes = [ProviderAuthentication]
    permission_classes = [IsCorrectProvider]

    def post(self, request, provider_name):
        """
        because of the authentication and permission classes we know that if we
        got here the api key is valid and the provider_name path variable
        matches the key
        """

        payload = request.data
        center = None

        match provider_name:
            case 'pickandpack':
                center = LogisticsCenterEnum.PICK_AND_PACK.name

        if center:
            raw_message_type = payload.get('type')
            message_type = None

            if raw_message_type == 'inboundStatusChange':
                message_type = LogisticsCenterMessageTypeEnum.INBOUND_STATUS_CHANGE.name
            elif raw_message_type == 'inboundReceipt':
                message_type = LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name
            elif raw_message_type == 'orderStatusChange':
                message_type = LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name
            elif raw_message_type == 'orderShippingStatusChange':
                message_type = LogisticsCenterMessageTypeEnum.SHIP_ORDER.name
            elif raw_message_type == 'snapshot':
                message_type = LogisticsCenterMessageTypeEnum.SNAPSHOT.name

            if message_type:
                # save raw message to database
                message = LogisticsCenterMessage.objects.create(
                    center=center,
                    message_type=message_type,
                    raw_body=json.dumps(payload),
                )

                # schedule async task to process the message
                process_logistics_center_message.apply_async((message.pk,))
            else:
                logger.error(f'failed to match message type {raw_message_type}')
                return Response(
                    {
                        'success': False,
                        'message': 'Bad message type.',
                        'code': 'bad_message_type',
                        'status': status.HTTP_400_BAD_REQUEST,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            logger.error(f'failed to match provider name {provider_name} with center')
            return Response(
                {
                    'success': False,
                    'message': 'Bad provider.',
                    'code': 'bad_provider',
                    'status': status.HTTP_400_BAD_REQUEST,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'success': True,
                'message': 'Payload accepted.',
                'status': status.HTTP_200_OK,
                'data': {},
            },
            status=status.HTTP_200_OK,
        )
