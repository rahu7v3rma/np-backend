from dal import autocomplete
from django import http


class BaseAutocompleteView(autocomplete.Select2QuerySetView):
    """
    this is a base autocomplete view class which ensures we reply to
    unauthorized requests in a similar manner to our normal views
    """

    def render_to_response(self, context):
        # make sure the request is authenticated since we can't use drf
        # authentication classes here. return our regular response structure
        # using base django tools
        if not self.request.user.is_authenticated:
            return http.JsonResponse(
                status=401,
                data={
                    'success': False,
                    'message': 'Unauthorized.',
                    'code': 'unauthorized',
                    'status': 401,
                    'data': {},
                },
            )

        return super().render_to_response(context)
