from django.urls import path

from health import views


urlpatterns = [
    path('livez', views.HealthView.as_view(), name='livez'),
    path('readyz', views.HealthView.as_view(), name='readyz'),
]
