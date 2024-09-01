from django.conf import settings
from django.core import mail
from django.test import TestCase

from services.email import send_mail


class EmailTestCase(TestCase):
    # All the backend mechanism testing is handled here:
    # https://github.com/django-ses/django-ses/blob/master/tests/test_backend.py
    def test_send_mail_success(self):
        res = send_mail(
            ['email@example.com'],
            'Test Email',
            context={'username': 'Test User', 'password': '12345678'},
            cc_emails=['cc@example.com'],
            bcc_emails=['bcc@example.com'],
            plaintext_email_template='emails/reset_password.txt',
            html_email_template='emails/reset_password.html',
        )
        self.assertTrue(res)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(mail.outbox[0].reply_to, [settings.REPLY_TO_EMAIL])
        self.assertEqual(mail.outbox[0].to, ['email@example.com'])
        self.assertEqual(mail.outbox[0].subject, 'Test Email')
        self.assertEqual(mail.outbox[0].cc, ['cc@example.com'])
        self.assertEqual(mail.outbox[0].bcc, ['bcc@example.com'])
