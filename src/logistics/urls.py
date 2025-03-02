from django.urls import path

from . import admin_views, views


urlpatterns = [
    path(
        'order-products',
        admin_views.AddProductsOrderView.as_view(),
        name='order-products',
    ),
    path(
        'order-products/<int:pk>',
        admin_views.AddProductsOrderView.as_view(),
        name='order-products',
    ),
    path(
        'order-products-status/<int:pk>',
        admin_views.UpdateStatusProductsOrderView.as_view(),
        name='order-products-status',
    ),
    path(
        '<str:provider_name>/webhook',
        views.ProviderWebhookView.as_view(),
        name='provider-webhook',
    ),
]
