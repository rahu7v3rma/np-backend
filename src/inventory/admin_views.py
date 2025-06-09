from django.db.models import Q

from common.admin_views import BaseAutocompleteView
from inventory.models import Brand, Category, Product, Supplier, Tag, Variation


class ProductSupplierAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return Supplier.objects.none()

        qs = Supplier.objects.all()

        if self.q:
            qs = qs.filter(name_he__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.name_he


class ProductBrandAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return Brand.objects.none()

        qs = Brand.objects.all()

        if self.q:
            qs = qs.filter(name_he__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.name_he


class ProductCategoryAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return Category.objects.none()

        qs = Category.objects.all()

        if self.q:
            qs = qs.filter(name_he__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.name_he


class ProductTagAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return Tag.objects.none()

        qs = Tag.objects.all()

        if self.q:
            qs = qs.filter(name_he__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.name_he


class ProductVariationAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return Variation.objects.none()

        qs = Variation.objects.all()

        if self.q:
            qs = qs.filter(system_name__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.system_name


class ProductAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return Product.objects.none()
        qs = Product.objects.exclude(product_kind='BUNDLE')
        if self.q:
            qs = qs.filter(Q(name_he__icontains=self.q) | Q(sku__icontains=self.q))

        return qs

    def get_result_label(self, result):
        return f'{result.name_he} | {result.sku}'
