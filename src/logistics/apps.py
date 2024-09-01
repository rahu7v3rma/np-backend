from django.apps import AppConfig


class LogisticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'logistics'
    verbose_name = 'Reports'

    def ready(self):
        from . import signals  # noqa: F401
