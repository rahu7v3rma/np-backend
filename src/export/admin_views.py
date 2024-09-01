import os

from django.core.files.storage import storages
from django.shortcuts import redirect
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView


class DownloadExportFile(APIView):
    # only admin sessions have access to this view
    authentication_classes = [SessionAuthentication]

    def get(self, request, export_file_name=None):
        storage = storages['exports']

        if export_file_name:
            private_export_file_name = storage.generate_filename(
                os.path.join(str(request.user.pk), export_file_name)
            )
        else:
            private_export_file_name = None

        if not private_export_file_name or not storage.exists(private_export_file_name):
            return Response(
                {
                    'success': False,
                    'message': 'Not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return redirect(storage.url(private_export_file_name))
