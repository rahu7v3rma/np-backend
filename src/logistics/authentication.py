from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.authentication import (
    BaseAuthentication,
    get_authorization_header,
)
from rest_framework.permissions import BasePermission


class ProviderAuthentication(BaseAuthentication):
    """
    Simple api key based authentication, validated via the settings

    Clients should authenticate by passing the api key in the "Authorization"
    HTTP header, prepended with the string "Bearer ".  For example:

        Authorization: Bearer 401f7ac837da42b97f613d789819ff93537bee6a
    """

    keyword = 'Bearer'

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None

        if len(auth) == 1:
            msg = _('Invalid bearer header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = _('Invalid bearer header. API key string should not contain spaces.')
            raise exceptions.AuthenticationFailed(msg)

        try:
            api_key = auth[1].decode()
        except UnicodeError:
            msg = _(
                'Invalid API key header. API key string should not contain '
                'invalid characters.'
            )
            raise exceptions.AuthenticationFailed(msg)

        return self.authenticate_credentials(api_key)

    def authenticate_credentials(self, key):
        provider_name = settings.LOGISTICS_PROVIDER_AUTHENTICATION_KEYS.get(key)

        if not provider_name:
            raise exceptions.AuthenticationFailed(_('Invalid API key.'))

        return (provider_name, key)

    def authenticate_header(self, request):
        return self.keyword


class IsCorrectProvider(BasePermission):
    """
    Allows access only to authenticated users.
    """

    def has_permission(self, request, view):
        return request.user == view.kwargs['provider_name']
