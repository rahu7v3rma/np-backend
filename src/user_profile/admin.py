from django.contrib import admin

from user_profile.models import Profile


@admin.register(Profile)
class UserProfileAdmin(admin.ModelAdmin):
    pass
