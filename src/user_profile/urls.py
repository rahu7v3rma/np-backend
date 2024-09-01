from django.urls import path

from user_profile import views


urlpatterns = [
    path('', views.UserProfileView.as_view(), name='user_profile'),
]
