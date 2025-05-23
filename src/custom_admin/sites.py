from django.conf import settings
from django.contrib import admin
from django.contrib.auth import REDIRECT_FIELD_NAME, get_user_model
from django.core.exceptions import ValidationError
from django.urls import path, reverse

from services.email import send_otp_token_email
from user_management.models import UserTwoFactorAuthData
from user_management.utils import user_two_factor_auth_data_create

from .views import AdminConfirmTwoFactorAuthView


class AdminSite(admin.AdminSite):
    def get_urls(self):
        base_urlpatterns = super().get_urls()

        extra_urlpatterns = [
            path(
                'confirm-2fa/',
                self.admin_view(AdminConfirmTwoFactorAuthView.as_view()),
                name='confirm-2fa',
            )
        ]

        return extra_urlpatterns + base_urlpatterns

    def login(self, request, *args, **kwargs):
        if not settings.OTP_ADMIN_ENABLED:
            return super().login(request, *args, **kwargs)

        if request.method != 'POST':
            return super().login(request, *args, **kwargs)

        username = request.POST.get('username')
        password = request.POST.get('password')
        user = get_user_model().objects.filter(username=username).first()

        if not user or not user.check_password(password):
            return super().login(request, *args, **kwargs)

        if not user.email:
            raise ValidationError('user email not found.')

        # Get the two factor auth data if exists
        two_factor_auth_data = UserTwoFactorAuthData.objects.filter(
            user__email=username
        ).first()

        # create the token if not found
        if two_factor_auth_data is None:
            two_factor_auth_data = user_two_factor_auth_data_create(user)

        # get token and send it to the user
        token = two_factor_auth_data.totp.now()
        send_otp_token_email(user.email, token)

        request.POST._mutable = True
        request.POST[REDIRECT_FIELD_NAME] = reverse('admin:confirm-2fa')
        request.POST._mutable = False

        return super().login(request, *args, **kwargs)

    def has_permission(self, request):
        has_perm = super().has_permission(request)
        if not settings.OTP_ADMIN_ENABLED or not has_perm:
            return has_perm
        two_factor_auth_data = UserTwoFactorAuthData.objects.filter(
            user=request.user
        ).first()
        allowed_paths = [reverse('admin:confirm-2fa')]
        if request.path in allowed_paths:
            return True

        if two_factor_auth_data is not None:
            two_factor_auth_token = request.session.get('2fa_token')
            return str(two_factor_auth_data.session_identifier) == two_factor_auth_token
        return False
