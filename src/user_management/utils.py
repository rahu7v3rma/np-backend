import hashlib

from django.conf import settings
import pyotp
from rest_framework.permissions import IsAuthenticated

from .models import UserTwoFactorAuthData


class InnerIsAuthenticated(IsAuthenticated):
    def has_permission(self, request, view):
        if (
            request.headers.get('X-INNER-AUTHORIZATION')
            in settings.INNER_AUTHORIZATION_KEYS
        ):
            return super().has_permission(request, view)
        else:
            return False


def hash_user_id(user_id):
    # hash and re-hash
    hashed_user_id = hashlib.sha256(user_id.encode('utf-8')).hexdigest()
    rehashed_user_id = hashlib.sha256(hashed_user_id.encode('utf-8')).hexdigest()

    return rehashed_user_id


def user_two_factor_auth_data_create(user):
    if hasattr(user, 'two_factor_auth_data'):
        return user.two_factor_auth_data

    two_factor_auth_data = UserTwoFactorAuthData.objects.create(
        user=user, otp_secret=pyotp.random_base32()
    )

    return two_factor_auth_data
