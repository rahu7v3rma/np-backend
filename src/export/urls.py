from django.urls import path

from . import admin_views


urlpatterns = [
    path(
        'download/<path:export_file_name>',
        admin_views.DownloadExportFile.as_view(),
        name='download_export_file_view',
    ),
    path(
        'download/',
        admin_views.DownloadExportFile.as_view(),
        name='download_export_file_view',
    ),
]
