from django.forms import ClearableFileInput


class ImageUploadWidget(ClearableFileInput):
    template_name = 'admin/widgets/image_upload.html'
