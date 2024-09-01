from datetime import datetime, timedelta, timezone

from django.conf import settings
import jwt


def jwt_encode(payload):
    try:
        if isinstance(payload, dict):
            payload['exp'] = datetime.now(timezone.utc) + timedelta(
                days=int(settings.JWT_EXPIRY_DAYS)
            )
            return jwt.encode(
                payload=payload,
                key=settings.JWT_SECRET_KEY,
                algorithm=settings.JWT_ALGORITHM,
            )
    except Exception:
        ...
    return None
