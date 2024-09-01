from django.urls import path

from payment import views


urlpatterns = [
    path(
        'payment-detail/',
        views.PaymentWebhookView.as_view(),
        name='payment-detail',
    ),
]
