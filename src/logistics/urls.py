from django.urls import path

from .views import AddProductsOrderView, UpdateStatusProductsOrderView


urlpatterns = [
    path(
        'order-products',
        AddProductsOrderView.as_view(),
        name='order-products',
    ),
    path(
        'order-products/<int:pk>',
        AddProductsOrderView.as_view(),
        name='order-products',
    ),
    path(
        'order-products-status/<int:pk>',
        UpdateStatusProductsOrderView.as_view(),
        name='order-products-status',
    ),
]
