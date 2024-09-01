from django.contrib.auth import get_user_model
from django.db import models


class Profile(models.Model):
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE, primary_key=True
    )
