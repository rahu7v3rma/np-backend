from django.db.models import Q

from common.admin_views import BaseAutocompleteView

from .models import Product


class BundledProductAutocompleteView(BaseAutocompleteView):
    def get_queryset(self):
        # return no results for unauthenticated requests
        if not self.request.user.is_authenticated:
            return Product.objects.none()

        qs = Product.objects.all()

        if self.q:
            qs = qs.exclude(product_kind=Product.ProductKindEnum.BUNDLE.name).filter(
                Q(sku__icontains=self.q)
                | Q(name_en__icontains=self.q)
                | Q(name_he__icontains=self.q)
            )

        return qs

    def get_result_label(self, result):
        return f'{result.sku} - {result.name}'
