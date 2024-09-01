from django.urls import path

from user_management import views


urlpatterns = [
    path('login', views.UserLoginView.as_view(), name='user_login'),
    path('logout', views.UserLogoutView.as_view(), name='user_logout'),
    path(
        'reset/request',
        views.ResetPasswordRequestView.as_view(),
        name='user_password_reset_request',
    ),
    path(
        'reset/verify',
        views.ResetPasswordVerifyView.as_view(),
        name='user_password_reset_verify',
    ),
    path(
        'reset/confirm',
        views.ResetPasswordConfirmView.as_view(),
        name='user_password_reset_confirm',
    ),
    path(
        'sign-up',
        views.SignUpView.as_view(),
        name='user_sign_up',
    ),
    path(
        'change-password',
        views.ChangePasswordView.as_view(),
        name='change_password',
    ),
    path(
        'inner/auth',
        views.InnerAuthView.as_view(),
        name='user_inner_auth',
    ),
]
