import os

from django.core.exceptions import ValidationError
from django.utils.html import format_html


def anchor_tag_popup(href, name):
    return format_html(
        '<a href="javascript:void(0);" '
        "onclick=\"window.open('{}?_to_field=id&_popup=1', "
        "'_blank', 'width=800, height=600')\">{}</a>",
        href,
        name,
    )


def validate_svg_image(file):
    ext = os.path.splitext(file.name)[1].lower()
    valid_extensions = ['.svg']
    if ext not in valid_extensions:
        raise ValidationError(
            'Unsupported file extension. Only .svg files are allowed.'
        )

    if file.content_type != 'image/svg+xml':
        raise ValidationError('Invalid file type. Only SVG files are allowed.')
