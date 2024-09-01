import os
import uuid

from django.db.models import FileField, ImageField, Model
from django.utils.encoding import filepath_to_uri
from storages.backends.s3boto3 import S3Boto3Storage
from storages.utils import clean_name

from .admin_utils import validate_svg_image
from .admin_widgets import ImageUploadWidget


class AllaPrimaStorage(S3Boto3Storage):
    def get_default_settings(self):
        super_settings = super().get_default_settings()
        super_settings.update(
            base_retrieve_url=None,
        )

        return super_settings

    def url(self, name, parameters=None, expire=None, http_method=None):
        if self.base_retrieve_url:
            # normalize the path
            name = self._normalize_name(clean_name(name))

            return f'{self.base_retrieve_url}/{filepath_to_uri(name)}'
        else:
            return super().url(name, parameters, expire, http_method)


class RandomNameImageField(ImageField):
    def __init__(self, *args, **kwargs):
        if not kwargs.get('upload_to'):
            kwargs['upload_to'] = RandomNameImageField._generate_random_file_name

        super().__init__(*args, **kwargs)

    @staticmethod
    def _generate_random_file_name(_instance: Model, original_file_name: str) -> str:
        ext = os.path.splitext(original_file_name)[1]
        random_file_name = f'{uuid.uuid4()}{ext}'
        return random_file_name

    def formfield(self, **kwargs):
        kwargs['widget'] = ImageUploadWidget
        return super().formfield(**kwargs)


class RandomNameImageFieldSVG(FileField):
    def __init__(self, *args, **kwargs):
        if not kwargs.get('upload_to'):
            kwargs['upload_to'] = RandomNameImageFieldSVG._generate_random_file_name

        super().__init__(*args, **kwargs)

    @staticmethod
    def _generate_random_file_name(_instance: Model, original_file_name: str) -> str:
        ext = os.path.splitext(original_file_name)[1]
        random_file_name = f'{uuid.uuid4()}{ext}'
        return random_file_name

    def formfield(self, **kwargs):
        kwargs['widget'] = ImageUploadWidget
        kwargs['validators'] = [validate_svg_image]
        return super().formfield(**kwargs)
