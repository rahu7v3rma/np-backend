import os

from celery import Celery


# set the default django settings module for the celery app
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'np_cms.settings')

app = Celery('np_cms')

# using a string here means the worker doesn't have to serialize the
# configuration object to child processes.
# namespace='CELERY' means all celery-related configuration keys should have a
# `CELERY_` prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# load task modules from all registered django apps
app.autodiscover_tasks()
