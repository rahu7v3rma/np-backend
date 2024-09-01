from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                'success': True,
                'message': 'Healthy.',
                'status': status.HTTP_200_OK,
                'data': {},
            },
            status=status.HTTP_200_OK,
        )
