"""np_cms URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as serve_static
import django_js_reverse.views


admin.site.site_header = 'Nicklas+'
admin.site.site_title = 'Nicklas+ Portal'
admin.site.index_title = 'Welcome to the Nicklas+ Portal'
admin.site.site_url = '/admin'


urlpatterns = [
    path('jsreverse/', django_js_reverse.views.urls_js, name='js_reverse'),
    path('health/', include('health.urls')),
    path('user/', include('user_management.urls')),
    path('campaign/', include('campaign.urls')),
    path('payment/', include('payment.urls')),
    path('inventory/', include('inventory.urls')),
    path('export/', include('export.urls')),
    path('logistics/', include('logistics.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# this isn't a great solution for production, but allows for a single service
# to serve everything needed for the admin interface. the path is copied from
# django.conf.urls.static.static
if settings.SERVE_STATIC:
    urlpatterns += [
        re_path(
            r'^%s(?P<path>.*)$' % re.escape(settings.STATIC_URL.lstrip('/')),
            serve_static,
            kwargs={'document_root': settings.STATIC_ROOT},
        ),
    ]

"""
urlpatterns += i18n_patterns(
    re_path(r'^admin/', admin.site.urls),
)
"""

urlpatterns += [
    re_path(r'^admin/', admin.site.urls),
]
