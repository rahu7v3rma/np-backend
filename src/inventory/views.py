from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import (
    Case,
    F,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from campaign.models import (
    EmployeeGroupCampaign,
    EmployeeGroupCampaignProduct,
    OrganizationProduct,
    QuickOffer,
)

from .models import Product, Supplier
from .serializers import (
    GetSupplierSerializer,
    ProductGetSerializer,
    ProductSerializer,
    ProductSkuSearchSerializer,
    SupplierSerializer,
)


class ProductView(APIView):
    # only admin sessions have access to this view. it is used by the campaign
    # create / edit wizard
    authentication_classes = [SessionAuthentication]

    def post(self, request):
        request_serializer = ProductGetSerializer(data=request.data)

        if not request_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_limit = request_serializer.validated_data.get('limit', 10)
        request_page = request_serializer.validated_data.get('page', 1)
        request_organization_id = request_serializer.validated_data.get(
            'organization_id'
        )
        request_price_min = request_serializer.validated_data.get('price_min', None)
        request_price_max = request_serializer.validated_data.get('price_max', None)
        request_org_price_min = request_serializer.validated_data.get(
            'organization_price_min', None
        )
        request_org_price_max = request_serializer.validated_data.get(
            'organization_price_max', None
        )
        request_brand_id = request_serializer.validated_data.get('brand_id', None)
        request_supplier_id = request_serializer.validated_data.get('supplier_id', None)
        request_category_id = request_serializer.validated_data.get('category_id', None)
        request_tag_ids = request_serializer.validated_data.get('tag_ids', None)
        request_employee_group_id = request_serializer.validated_data.get(
            'employee_group_id', None
        )
        request_quick_offer_id = request_serializer.validated_data.get(
            'quick_offer_id', None
        )
        request_campaign_id = request_serializer.validated_data.get('campaign_id', None)
        request_product_kind = request_serializer.validated_data.get(
            'product_kind', None
        )
        request_query = request_serializer.validated_data.get('query', None)
        request_product_ids = request_serializer.validated_data.get('product_ids', None)
        request_google_price_min = request_serializer.validated_data.get(
            'google_price_min', None
        )
        request_google_price_max = request_serializer.validated_data.get(
            'google_price_max', None
        )

        products = Product.objects.filter(active=True)

        organization_price_subquery = Subquery(
            OrganizationProduct.objects.filter(
                organization=request_organization_id,
                product=OuterRef('id'),
            )
            .annotate(
                calculated_price=Case(
                    When(price__gt=0, then='price'),
                    default=OuterRef('sale_price'),
                )
            )
            .values('calculated_price')[:1]
        )

        products = products.annotate(
            calculated_price=Coalesce(organization_price_subquery, F('sale_price'))
        )

        if request_price_min:
            products = products.filter(total_cost__gte=request_price_min)
        if request_price_max:
            products = products.filter(total_cost__lte=request_price_max)
        if request_org_price_min:
            products = products.filter(calculated_price__gte=request_org_price_min)
        if request_org_price_max:
            products = products.filter(calculated_price__lte=request_org_price_max)
        if request_google_price_min:
            products = products.filter(google_price__gte=request_google_price_min)
        if request_google_price_max:
            products = products.filter(google_price__lte=request_google_price_max)
        if request_brand_id:
            products = products.filter(brand_id=request_brand_id)
        if request_supplier_id:
            products = products.filter(supplier_id=request_supplier_id)
        if request_category_id:
            products = products.filter(categories__id=request_category_id)
        if request_tag_ids:
            products = products.filter(tags__id__in=request_tag_ids)
        if request_product_kind:
            products = products.filter(product_kind=request_product_kind)
        if request_employee_group_id:
            employee_group_campaign = EmployeeGroupCampaign.objects.filter(
                campaign=request_campaign_id, employee_group=request_employee_group_id
            ).first()

            products = Product.objects.filter(
                employeegroupcampaignproduct__employee_group_campaign_id=employee_group_campaign.id
            )
        if request_query:
            products = products.filter(
                Q(name_en__icontains=request_query)
                | Q(name_he__icontains=request_query)
            )
        if request_product_ids:
            products = products.filter(id__in=request_product_ids)
        if request_quick_offer_id:
            quick_offer = QuickOffer.objects.filter(id=request_quick_offer_id).first()
            if quick_offer:
                quick_offer_selected_products = list(
                    quick_offer.selected_products.values_list('id', flat=True)
                )
                if not quick_offer_selected_products:
                    quick_offer_selected_products.append(None)
                products = products.filter(id__in=quick_offer_selected_products)

        paginator = Paginator(products.order_by('id').all(), request_limit)
        page = paginator.get_page(request_page)

        products_serializer = ProductSerializer(page, many=True)

        return Response(
            {
                'success': True,
                'message': 'Products fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    'page_data': products_serializer.data,
                    'page_num': page.number,
                    'has_more': page.has_next(),
                    'total_count': paginator.count,
                },
            },
            status=status.HTTP_200_OK,
        )


class SupplierView(APIView):
    authentication_classes = [SessionAuthentication]

    def get(self, request):
        serializer = SupplierSerializer(Supplier.objects.all(), many=True)

        return Response(
            {
                'success': True,
                'message': 'list of Suppliers fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class SupplierProductsView(APIView):
    authentication_classes = [SessionAuthentication]

    def get(self, request):
        request_serializer = GetSupplierSerializer(data=request.GET)
        if not request_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        supplier_name = request_serializer.validated_data['name']
        supplier = Supplier.objects.filter(name=supplier_name).first()
        if not supplier:
            return Response(
                {
                    'success': False,
                    'message': 'Supplier not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        # Get all products for the supplier
        products = supplier.supplier_products.annotate(
            tax_percent=Value(settings.TAX_PERCENT)
        ).all()

        # Create a list to store products with voucher values
        products_with_voucher = []
        # Iterate through each product
        for product in products:
            # Get the base product data
            serializer = ProductSerializer(product)
            product_data = serializer.data

            # Only process products with type 'MONEY'
            if product.product_kind == 'MONEY':
                # Calculate voucher_value for the product
                # Check if the product is associated with any
                # EmployeeGroupCampaignProduct
                campaign_products = EmployeeGroupCampaignProduct.objects.filter(
                    product_id=product.id
                )

                for campaign_product in campaign_products:
                    # Create a copy of the product data
                    # Use the serializer to convert the product to a dictionary
                    product_with_voucher = product_data.copy()
                    # Calculate voucher value based on campaign settings
                    voucher_value = 0
                    if (
                        campaign_product.employee_group_campaign_id
                        and (
                            campaign_product.employee_group_campaign_id
                        ).budget_per_employee
                    ):
                        if campaign_product.discount_mode == 'EMPLOYEE':
                            voucher_value = (
                                campaign_product.employee_group_campaign_id.budget_per_employee
                                / (
                                    1
                                    - (
                                        (
                                            campaign_product.organization_discount_rate
                                            or 0
                                        )
                                        / 100
                                    )
                                )
                            )
                        else:
                            voucher_value = (
                                campaign_product.employee_group_campaign_id
                            ).budget_per_employee

                    # Add voucher_value to the product data
                    product_with_voucher['voucher_value'] = str(
                        round(float(voucher_value), 2)
                    )

                    # Add the product with voucher value to the list
                    products_with_voucher.append(product_with_voucher)
            else:
                # For non-MONEY products, just add them as is
                products_with_voucher.append(product_data)

        # If no products with voucher values were found, use the original products
        if not products_with_voucher:
            serializer = ProductSerializer(products, many=True)
            products_with_voucher = serializer.data
        return Response(
            {
                'success': True,
                'message': 'Products fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': products_with_voucher,
            },
            status=status.HTTP_200_OK,
        )


class ProductSkuSearchView(APIView):
    authentication_classes = [SessionAuthentication]

    def get(self, request):
        request_serializer = ProductSkuSearchSerializer(data=request.GET)
        if not request_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        query = request_serializer.validated_data.get('q')
        skus = list(
            Product.objects.exclude(
                product_kind=Product.ProductKindEnum.BUNDLE.name,
            )
            .filter(
                sku__icontains=query,
            )[:20]
            .values_list('sku', flat=True)
        )
        return Response(
            {
                'success': True,
                'message': 'Products fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': skus,
            },
            status=status.HTTP_200_OK,
        )
