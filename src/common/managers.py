from django.db import models


class ActiveObjectsManager(models.Manager):
    """Active Objects manager."""

    def get_queryset(self):
        """
        Return active objects of model.
        """
        return super().get_queryset().filter(is_deleted=False)
