from django.contrib import messages
from rest_framework.reverse import reverse as drf_reverse

from .tasks import export_products_as_xlsx as export_products_as_xlsx_task


class ProductActionsMixin:
    def export_as_xlsx(self, request, queryset):
        # using the inner query since it can be pickled to recreate the
        # queryset (celery is in charge of pickling here), based on docs -
        # https://docs.djangoproject.com/en/5.1/ref/models/querysets/#pickling-querysets
        export_products_as_xlsx_task.apply_async(
            (
                queryset.query,
                request.user.pk,
                request.user.email,
                drf_reverse('download_export_file_view', request=request),
            )
        )

        self.message_user(
            request,
            f'Exporting products, file will be sent to '
            f'"{request.user.email}" when ready',
            messages.SUCCESS,
        )
