from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as AuthUserAdmin
from rest_framework.authtoken.models import TokenProxy

from user_management.models import Admin


UserModel = get_user_model()

admin.site.unregister(UserModel)
admin.site.unregister(TokenProxy)


class BaseUserAdmin(AuthUserAdmin):
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'is_staff',
        'is_active',
    )


@admin.register(Admin)
class AdminAdmin(BaseUserAdmin):
    # users should not be created via the admin site. instead they should
    # always sign up via the signup view to make sure they are initialized
    # properly
    def has_add_permission(self, request):
        return False
