"""
WSGI config for np_cms project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/wsgi/
"""

import logging
import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'np_cms.settings')

application = get_wsgi_application()


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # filter out only if method is get, url starts with /health/
        # and status is 200
        return not (
            record.args['m'] == 'GET'
            and record.args['U'].startswith('/health/')
            and record.args['s'] == '200'
        )


# add filter to prevent health check requests from being logged to the
# access log
gunicorn_logger = logging.getLogger('gunicorn.access').addFilter(HealthCheckFilter())
