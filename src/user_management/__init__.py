from rest_framework import HTTP_HEADER_ENCODING, authentication


# copied and repurposed from
# https://github.com/encode/django-rest-framework/blob/a1b35bb44b7c9251c8b7bc995aa6598044f1d3ef/rest_framework/authentication.py#L14
def get_authorization_header(request):
    auth = request.META.get('HTTP_X_AUTHORIZATION', b'') or request.META.get(
        'HTTP_AUTHORIZATION', b''
    )
    if isinstance(auth, str):
        auth = auth.encode(HTTP_HEADER_ENCODING)
    return auth


# monkey-patch get_authorization_header to override the header which should
# contain the authorization token. this is done because of some issues with
# safari which prevent the "Authorization" header from being copied properly
# when a redirect occurs and which affects react native implementations
# attempting to request data from this service
authentication.get_authorization_header = get_authorization_header
