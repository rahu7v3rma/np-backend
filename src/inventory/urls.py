from django.urls import path

from .admin_views import (
    ProductAutocompleteView,
    ProductBrandAutocompleteView,
    ProductCategoryAutocompleteView,
    ProductSupplierAutocompleteView,
    ProductTagAutocompleteView,
    ProductVariationAutocompleteView,
)
from .views import (
    ProductSkuSearchView,
    ProductView,
    SupplierProductsView,
    SupplierView,
)


urlpatterns = [
    path(
        'product',
        ProductView.as_view(),
        name='product',
    ),
    path(
        'suppliers',
        SupplierView.as_view(),
        name='suppliers',
    ),
    path(
        'supplier-products',
        SupplierProductsView.as_view(),
        name='supplier-products',
    ),
    path(
        'product-sku-search',
        ProductSkuSearchView.as_view(),
        name='product-sku-search',
    ),
    path(
        'supplier-product-autocomplete',
        ProductSupplierAutocompleteView.as_view(),
        name='supplier-product-autocomplete',
    ),
    path(
        'brand-product-autocomplete',
        ProductBrandAutocompleteView.as_view(),
        name='brand-product-autocomplete',
    ),
    path(
        'category-product-autocomplete',
        ProductCategoryAutocompleteView.as_view(),
        name='category-product-autocomplete',
    ),
    path(
        'tag-product-autocomplete',
        ProductTagAutocompleteView.as_view(),
        name='tag-product-autocomplete',
    ),
    path(
        'variation-product-autocomplete',
        ProductVariationAutocompleteView.as_view(),
        name='variation-product-autocomplete',
    ),
    path(
        'product-autocomplete',
        ProductAutocompleteView.as_view(),
        name='product-autocomplete',
    ),
]
