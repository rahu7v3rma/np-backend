from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from logistics.models import LogisticsCenterMessage


class ProviderWebhookTestCase(TestCase):
    def test_provider_webhook_authentication_bad_token(self):
        client = APIClient()

        response = client.post(
            '/logistics/provider-name/webhook',
            format='json',
            data={},
        )
        self.assertEqual(response.status_code, 401)

        client.credentials(HTTP_AUTHORIZATION='nope')
        response = client.post(
            '/logistics/provider-name/webhook',
            format='json',
            data={},
        )
        self.assertEqual(response.status_code, 401)

        client.credentials(HTTP_AUTHORIZATION='Bearer nope')
        response = client.post(
            '/logistics/provider-name/webhook',
            format='json',
            data={},
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(
        LOGISTICS_PROVIDER_AUTHENTICATION_KEYS={
            'right-provider-token': 'right-provider'
        },
    )
    def test_provider_webhook_authentication_provider_mismatch(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer right-provider-token')

        response = client.post(
            '/logistics/wrong-provider/webhook',
            format='json',
            data={},
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(
        LOGISTICS_PROVIDER_AUTHENTICATION_KEYS={
            'unsupported-provider-token': 'unsupported-provider'
        },
    )
    def test_provider_webhook_unsupported_provider(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer unsupported-provider-token')

        response = client.post(
            '/logistics/unsupported-provider/webhook',
            format='json',
            data={'type': 'inboundReceipt', 'data': {}},
        )

        # request was not successful and no messages were created
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'bad_provider')
        self.assertEquals(len(LogisticsCenterMessage.objects.all()), 0)

    @override_settings(
        LOGISTICS_PROVIDER_AUTHENTICATION_KEYS={
            'supported-provider-token': 'supported-provider'
        },
    )
    def test_provider_webhook_unsupported_center(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer supported-provider-token')

        response = client.post(
            '/logistics/supported-provider/webhook',
            format='json',
            data={'type': 'inboundReceipt', 'data': {}},
        )

        # request was not successful and no messages were created
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'bad_provider')
        self.assertEquals(len(LogisticsCenterMessage.objects.all()), 0)

    @override_settings(
        LOGISTICS_PROVIDER_AUTHENTICATION_KEYS={'pickandpack-token': 'pickandpack'},
    )
    def test_provider_webhook_bad_message_type(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer pickandpack-token')

        response = client.post(
            '/logistics/pickandpack/webhook',
            format='json',
            data={},
        )

        # request was not successful and no messages were created
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'bad_message_type')
        self.assertEquals(len(LogisticsCenterMessage.objects.all()), 0)

        response = client.post(
            '/logistics/pickandpack/webhook',
            format='json',
            data={'type': 'wrongType', 'data': {}},
        )

        # request was not successful and no messages were created
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'bad_message_type')
        self.assertEquals(len(LogisticsCenterMessage.objects.all()), 0)

    @override_settings(
        LOGISTICS_PROVIDER_AUTHENTICATION_KEYS={'pickandpack-token': 'pickandpack'},
    )
    @patch('logistics.views.process_logistics_center_message')
    def test_provider_webhook_valid_message(
        self, mock_process_logistics_center_message
    ):
        # mock is not called to begin with
        self.assertEquals(
            mock_process_logistics_center_message.apply_async.call_count, 0
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer pickandpack-token')

        response = client.post(
            '/logistics/pickandpack/webhook',
            format='json',
            data={'type': 'inboundReceipt', 'data': {}},
        )

        # request was successful, a message was created and a process task was
        # queued
        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(LogisticsCenterMessage.objects.all()), 1)
        self.assertEquals(
            mock_process_logistics_center_message.apply_async.call_count, 1
        )

        response = client.post(
            '/logistics/pickandpack/webhook',
            format='json',
            data={'type': 'orderStatusChange', 'data': {}},
        )

        # request was successful, another message was created and another
        # process task was queued
        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(LogisticsCenterMessage.objects.all()), 2)
        self.assertEquals(
            mock_process_logistics_center_message.apply_async.call_count, 2
        )

        response = client.post(
            '/logistics/pickandpack/webhook',
            format='json',
            data={'type': 'snapshot', 'data': {}},
        )

        # request was successful, another message was created and another
        # process task was queued
        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(LogisticsCenterMessage.objects.all()), 3)
        self.assertEquals(
            mock_process_logistics_center_message.apply_async.call_count, 3
        )
