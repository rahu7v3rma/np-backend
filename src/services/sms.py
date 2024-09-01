from django.conf import settings
import requests


def _send_sms(from_name: str, content: str, to: list[str]):
    res = requests.post(
        f'{settings.SMS_ACTIVETRAIL_BASE_URL}/api/smscampaign/OperationalMessage',
        headers={'Authorization': settings.SMS_ACTIVETRAIL_API_KEY},
        json={
            'details': {
                'can_unsubscribe': False,
                'name': 'Nicklas',  # not sure what effect this has
                'from_name': from_name,
                'content': content,
            },
            'scheduling': {'send_now': True},
            'mobiles': [{'phone_number': p} for p in to],
        },
    )

    return res.status_code == 200


def send_otp_token_sms(phone_number: str, otp_token: str):
    res = _send_sms('Nicklas+', f'Your OTP code is: {otp_token}', [phone_number])
    return res


def send_campaign_welcome_sms(sender_name: str, phone_number: str, message: str):
    res = _send_sms(
        sender_name,
        message,
        [phone_number],
    )
    return res
