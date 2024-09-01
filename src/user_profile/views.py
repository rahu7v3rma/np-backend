from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from user_profile.serializers import ProfileSerializer


class UserProfileView(APIView):
    def get(self, request):
        if not hasattr(request.user, 'profile'):
            return Response(
                {
                    'success': False,
                    'message': 'Profile does not exist.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProfileSerializer(request.user.profile)
        return Response(
            {
                'success': True,
                'message': 'User profile fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )
