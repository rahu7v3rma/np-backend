import uuid

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import UserManager
from django.contrib.auth.tokens import default_token_generator
from django.db import models
import pyotp


# user model used for auth
UserModel = get_user_model()

# token generator
TOKEN_GENERATOR = default_token_generator


class ResetPasswordToken(models.Model):
    class Meta:
        verbose_name = 'Password Reset Token'
        verbose_name_plural = 'Password Reset Tokens'

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        UserModel,
        related_name='password_reset_tokens',
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    token = models.CharField(max_length=255, db_index=True, unique=True)
    ip_address = models.GenericIPAddressField(default='', blank=True, null=True)
    user_agent = models.CharField(max_length=256, default='', blank=True)

    def _generate_token(self):
        return TOKEN_GENERATOR.make_token(self.user)

    def verify(self):
        return TOKEN_GENERATOR.check_token(self.user, self.token)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self._generate_token()

        return super().save(*args, **kwargs)


class AdminManager(UserManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_staff=True)


class Admin(UserModel):
    objects = AdminManager()

    class Meta:
        proxy = True


class UserTwoFactorAuthData(models.Model):
    user = models.OneToOneField(
        UserModel, related_name='two_factor_auth_data', on_delete=models.CASCADE
    )
    otp_secret = models.CharField(max_length=255)
    session_identifier = models.UUIDField(blank=True, null=True)

    def validate_otp(self, otp: str):
        return self.totp.verify(otp)

    def rotate_session_identifier(self):
        self.session_identifier = uuid.uuid4()
        self.save(update_fields=['session_identifier'])

    def save(self, *args, **kwargs):
        self.otp_secret = (
            Fernet(settings.OTP_FERNET_KEY.encode())
            .encrypt(self.otp_secret.encode())
            .decode()
        )
        super().save(*args, **kwargs)

    @property
    def totp(self):
        return pyotp.TOTP(
            Fernet(settings.OTP_FERNET_KEY.encode()).decrypt(self.otp_secret).decode(),
            interval=settings.OTP_INTERVAL,
        )
