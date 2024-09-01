from functools import wraps

from django.utils import translation
from rest_framework import status
from rest_framework.response import Response

from campaign.serializers import LangSerializer


def lang_decorator(api_view):
    @wraps(api_view)
    def wrapped_api_view(request, *args, **kwargs):
        lang_serializer = LangSerializer(data=request.GET)

        if not lang_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': lang_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lang = lang_serializer.validated_data.get('lang')

        if lang:
            translation.activate(lang)

        return api_view(request, *args, **kwargs)

    return wrapped_api_view
