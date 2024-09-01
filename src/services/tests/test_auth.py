from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.test import TestCase
import jwt

from services.auth import jwt_encode


class JwtEncodeTestCase(TestCase):
    def test_payload_non_dict(self):
        token = jwt_encode('string')
        assert token is None

    def test_payload_dict(self):
        payload = {'employee_id': 1}
        token = jwt_encode({'employee_id': 1})
        expected_expiry = int(
            (
                datetime.now(timezone.utc)
                + timedelta(days=int(settings.JWT_EXPIRY_DAYS))
            ).timestamp()
        )
        try:
            decoded_token = jwt.decode(
                jwt=token,
                key=settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            assert 'employee_id' in decoded_token
            assert decoded_token.get('employee_id') == payload['employee_id']
            assert 'exp' in decoded_token
            assert decoded_token['exp'] == expected_expiry
        except Exception:
            assert False
