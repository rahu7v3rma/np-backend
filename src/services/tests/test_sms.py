from django.conf import settings
from django.test import TestCase
import responses

from services.sms import _send_sms


class SMSTestCase(TestCase):
    @responses.activate
    def test_send_sms_success(self):
        responses.add(
            responses.POST,
            f'{settings.SMS_ACTIVETRAIL_BASE_URL}/api/smscampaign/OperationalMessage',
        )

        res = _send_sms('TEST', 'Test content', '000')

        self.assertTrue(res)
