from django import forms


class ModelWithImagesXlsxImportForm(forms.Form):
    """
    We will be importing images alongside model data, so let the user upload
    a directory with images which we will use when image file names are listed
    in the xlsx data
    """

    xlsx_file = forms.FileField(
        required=False, widget=forms.FileInput(attrs={'accept': '.xlsx'})
    )
    image_dir = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'webkitdirectory': True, 'directory': True}),
    )
