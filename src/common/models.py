from django.db import models
from django.utils import timezone


class TimeStampMixin(models.Model):
    """
    A mixin that adds `created_at` and `updated_at` timestamp fields to a
    model, along with automatic updating of the `updated_at` field whenever an
    instance of the model is saved.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Overrides the default `save` method to automatically update the
        `updated_at` field whenever an instance of the model is saved.
        """
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class IsDeletedMixin(models.Model):
    """
    A mixin that adds `is_deleted` field to a model, along with methods to
    delete/undelete instances of the model.
    """

    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def soft_delete(self, *args, **kwargs):
        """
        Deletes (sets `is_deleted` to `True`) the current instance of the model.
        """
        self.is_deleted = True
        self.save(update_fields=['is_deleted'])

    def undelete(self, *args, **kwargs):
        """
        Undeletes (sets `is_deleted` to `False`) the current instance of the model.
        """
        self.is_deleted = False
        self.save(update_fields=['is_deleted'])


class BaseModelMixin(TimeStampMixin, IsDeletedMixin):
    """
    A base model mixin that combines:
    - `TimeStampMixin`
    - `IsDeletedMixin`
    """

    class Meta:
        abstract = True
