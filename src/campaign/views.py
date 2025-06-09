from datetime import datetime, timezone
import logging
from time import time

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import (
    Case,
    CharField,
    DecimalField,
    F,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Concat
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from rest_framework import status
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from campaign.decorators import lang_decorator
from campaign.models import (
    Campaign,
    CampaignEmployee,
    CampaignImpersonationToken,
    Cart,
    CartProduct,
    Employee,
    EmployeeGroup,
    EmployeeGroupCampaign,
    EmployeeGroupCampaignProduct,
    Order,
    OrderProduct,
    Organization,
    OrganizationProduct,
    QuickOffer,
    QuickOfferSelectedProduct,
)
from campaign.serializers import (
    CampaignEmployeeSendInvitationPostSerializer,
    CampaignExchangeRequestSerializer,
    CampaignExtendedSerializer,
    CampaignProductsGetSerializer,
    CampaignSerializer,
    CartAddProductSerializer,
    CartSerializer,
    EmployeeGroupCampaignProductPutSerializer,
    EmployeeGroupSerializer,
    EmployeeLoginSerializer,
    EmployeeOrderRequestSerializer,
    EmployeeSerializer,
    EmployeeWithGroupSerializer,
    FilterLookupBrandsSerializer,
    FilterLookupProductKindsSerializer,
    FilterLookupSerializer,
    FilterLookupTagsSerializer,
    OrderSerializer,
    OrganizationLoginSerializer,
    OrganizationProductPutSerializer,
    OrganizationSerializer,
    ProductSerializerCampaign,
    QuickOfferProductRequestSerializer,
    QuickOfferProductSerializer,
    QuickOfferProductsRequestSerializer,
    QuickOfferProductsResponseSerializer,
    QuickOfferReadOnlySerializer,
    QuickOfferSelectProductsDetailSerializer,
    QuickOfferSelectProductsSerializer,
    QuickOfferSerializer,
    QuickOfferUpdateSendMyOrderSerializer,
    ShareRequestSerializer,
)
from campaign.tasks import send_campaign_employee_invitation
from campaign.utils import (
    AdminPreviewAuthentication,
    EmployeeAuthentication,
    EmployeeOrQuickOfferPermission,
    EmployeePermissions,
    QuickOfferAuthentication,
    QuickOfferPermissions,
    filter_campaign_products_with_calculated_price,
    get_campaign_brands,
    get_campaign_max_product_price,
    get_campaign_product_kinds,
    get_campaign_tags,
    get_employee_admin_preview,
    get_employee_impersonated_by,
    get_quick_offer_max_product_price,
    transform_variations,
)
from inventory.models import (
    Brand,
    Category,
    CategoryProduct,
    Product,
    Share,
    ShareTypeEnum,
    Supplier,
    Tag,
)
from inventory.serializers import (
    BrandSerializer,
    CategorySerializer,
    SupplierSerializer,
    TagSerializer,
)
from payment.utils import initiate_payment
from services.auth import jwt_encode
from services.email import send_order_confirmation_email, send_otp_token_email
from services.sms import send_otp_token_sms


logger = logging.getLogger(__name__)


class CampaignView(APIView):
    authentication_classes = [EmployeeAuthentication, AdminPreviewAuthentication]
    permission_classes = [AllowAny]

    @method_decorator(lang_decorator)
    def get(self, request, campaign_code):
        campaign = (
            Campaign.objects.filter(code=campaign_code)
            .prefetch_related(
                'organization', 'employeegroupcampaign_set__employee_group'
            )
            .first()
        )

        if not campaign:
            return Response(
                {
                    'success': False,
                    'message': 'Campaign does not exist.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if (
            request.user
            and isinstance(request.user, Employee)
            and not getattr(request.user, 'is_anonymous', False)
            and campaign.status == Campaign.CampaignStatusEnum.ACTIVE.name
        ):
            employee_group_campaign = EmployeeGroupCampaign.objects.filter(
                campaign=campaign, employee_group=request.user.employee_group
            ).first()

            if not get_employee_admin_preview(request.user):
                existing_order = Order.objects.filter(
                    campaign_employee_id__employee=request.user,
                    campaign_employee_id__campaign=campaign,
                    status=Order.OrderStatusEnum.PENDING.name,
                ).first()
            else:
                existing_order = None

            serializer = CampaignExtendedSerializer(
                campaign,
                context={
                    'employee': request.user,
                    'employee_group_campaign': employee_group_campaign,
                    'existing_order': existing_order,
                },
            )
        else:
            serializer = CampaignSerializer(campaign)

        return Response(
            {
                'success': True,
                'message': 'Campaign fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class CampaignEmployeeSelectionView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    @method_decorator(lang_decorator)
    def get(self, request, campaign_code):
        campaign: Campaign = Campaign.objects.get(code=campaign_code)

        employee_list = []

        pending_orders = Order.objects.filter(
            campaign_employee_id__campaign=campaign,
            status__in=[
                Order.OrderStatusEnum.PENDING.name,
                Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
            ],
        )
        employees = (
            campaign.campaignemployee_set.select_related('employee')
            .annotate(
                full_name=Concat(
                    'employee__first_name',
                    Value(' '),
                    'employee__last_name',
                    output_field=CharField(),
                ),
                employee_group=F('employee__employee_group__name'),
            )
            .exclude(
                employee__id__in=pending_orders.values_list(
                    'campaign_employee_id__employee__id', flat=True
                )
            )
        )

        for orders_data in pending_orders:
            employee_list.append(
                {
                    'has_order': True,
                    'employee_name': (
                        orders_data.campaign_employee_id.employee.full_name
                    ),
                    'employee_group': (
                        orders_data.campaign_employee_id.employee.employee_group.name
                    ),
                    'order_date_time': orders_data.order_date_time,
                    'product_names': orders_data.ordered_product_names(),
                    'product_kind': orders_data.ordered_product_kinds(),
                    'added_cost': orders_data.cost_added,
                    'extra_money': True if orders_data.cost_added > 0 else False,
                }
            )

        for employee in employees:
            employee_list.append(
                {
                    'has_order': False,
                    'employee_name': employee.full_name,
                    'order_date_time': None,
                    'employee_group': employee.employee_group,
                    'last_login': employee.last_login,
                    'product_names': '',
                    'product_kind': '',
                    'added_cost': 0,
                    'extra_money': False,
                }
            )

        return Response(
            {
                'success': True,
                'message': 'Campaign employee selection fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': employee_list,
            },
            status=status.HTTP_200_OK,
        )


class CampaignCategoriesView(APIView):
    authentication_classes = [EmployeeAuthentication, AdminPreviewAuthentication]
    permission_classes = [EmployeePermissions]

    @method_decorator(lang_decorator)
    def get(self, request, campaign_code):
        employee = EmployeeSerializer(request.user)

        employee_group_campaign_query = EmployeeGroupCampaign.objects.select_related(
            'campaign'
        ).filter(
            campaign__code=campaign_code,
            employee_group__pk=employee.data.get('employee_group', {}).get('id'),
        )

        if not get_employee_admin_preview(request.user):
            employee_group_campaign_query = employee_group_campaign_query.filter(
                campaign__status__in=[
                    Campaign.CampaignStatusEnum.ACTIVE.name,
                    Campaign.CampaignStatusEnum.PREVIEW.name,
                ]
            )

        employee_group_campaign = employee_group_campaign_query.first()

        if not employee_group_campaign:
            return Response(
                {
                    'success': False,
                    'message': 'Campaign not found.',
                    'code': 'campaign_not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        employee_group_campaign_products = EmployeeGroupCampaignProduct.objects.filter(
            employee_group_campaign_id=employee_group_campaign.id
        )
        product_ids = [
            product.product_id_id for product in employee_group_campaign_products
        ]
        categories_id = CategoryProduct.objects.filter(
            product_id__in=product_ids
        ).values_list('category_id', flat=True)
        categories = Category.objects.filter(id__in=categories_id)
        serialized_categories = CategorySerializer(categories, many=True).data

        return Response(
            {
                'success': True,
                'message': 'Categories fetched successfully.',
                'code': 'categories_fetched',
                'status': status.HTTP_200_OK,
                'data': {'categories': serialized_categories},
            },
            status=status.HTTP_200_OK,
        )


class EmployeeGroupView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def get(self, request, organization_id):
        if organization_id:
            employee_groups = Organization.objects.get(
                id=organization_id
            ).employeegroup_set.all()
        else:
            employee_groups = EmployeeGroup.objects.all()
        serializer = EmployeeGroupSerializer(employee_groups, many=True)

        return Response(
            {
                'success': True,
                'message': 'employee groups fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class ProductView(APIView):
    authentication_classes = [EmployeeAuthentication, AdminPreviewAuthentication]
    permission_classes = [EmployeePermissions]

    @method_decorator(lang_decorator)
    def get(self, request, campaign_code, product_id):
        employee_product_query = EmployeeGroupCampaignProduct.objects.filter(
            employee_group_campaign_id__campaign__code=campaign_code,
            employee_group_campaign_id__employee_group=request.user.employee_group,
            product_id=product_id,
        )

        if not get_employee_admin_preview(request.user):
            employee_product_query = employee_product_query.filter(
                employee_group_campaign_id__campaign__status__in=[
                    Campaign.CampaignStatusEnum.ACTIVE.name,
                    Campaign.CampaignStatusEnum.PREVIEW.name,
                ]
            )

        employee_product = employee_product_query.first()

        if not employee_product:
            return Response(
                {
                    'success': False,
                    'message': 'Product does not exist.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProductSerializerCampaign(
            employee_product.product_id,
            context={
                'campaign': employee_product.employee_group_campaign_id.campaign,
                'employee': request.user.employee_group,
            },
        )

        return Response(
            {
                'success': True,
                'message': 'Product data fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class ShareProductView(APIView):
    authentication_classes = [EmployeeAuthentication, AdminPreviewAuthentication]
    serializer = ShareRequestSerializer
    permission_classes = [EmployeePermissions]

    @method_decorator(lang_decorator)
    def post(self, request, campaign_code):
        serializer = ShareRequestSerializer(data=request.data)
        employee = request.user
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product_ids = serializer.data.get('product_ids')
        share_type = serializer.data.get('share_type')
        campaign = Campaign.objects.filter(
            code=campaign_code,
            status__in=[
                Campaign.CampaignStatusEnum.ACTIVE.name,
                Campaign.CampaignStatusEnum.PREVIEW.name,
            ],
        ).first()
        if not campaign:
            return Response(
                {
                    'success': False,
                    'message': 'Campaign not found or inactive.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        campaign_employee = CampaignEmployee.objects.filter(
            campaign=campaign, employee=employee
        ).first()
        if not campaign_employee:
            return Response(
                {
                    'success': False,
                    'message': 'Campaign employee association not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not isinstance(product_ids, list):
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': {'product_ids': ['A valid list of integers is required.']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Validate share type
        valid_share_types = [choice.value for choice in ShareTypeEnum]
        if share_type not in valid_share_types:
            return Response(
                {
                    'success': False,
                    'message': 'Invalid share type provided.',
                    'code': 'invalid_share_type',
                    'status': status.HTTP_400_BAD_REQUEST,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Handle Cart share type
        if share_type == ShareTypeEnum.Cart.value:
            campaign = Campaign.objects.filter(
                code=campaign_code,
                status__in=[
                    Campaign.CampaignStatusEnum.ACTIVE.name,
                    Campaign.CampaignStatusEnum.PREVIEW.name,
                ],
            ).first()
            if not campaign:
                return Response(
                    {
                        'success': False,
                        'message': 'Campaign not found or inactive.',
                        'code': 'not_found',
                        'status': status.HTTP_404_NOT_FOUND,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            campaign_employee = CampaignEmployee.objects.filter(
                campaign=campaign, employee=employee
            ).first()
            if not campaign_employee:
                return Response(
                    {
                        'success': False,
                        'message': 'Campaign employee association not found.',
                        'code': 'not_found',
                        'status': status.HTTP_404_NOT_FOUND,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            try:
                cart = Cart.objects.filter(
                    campaign_employee_id=campaign_employee.id
                ).first()
                product_ids = CartProduct.objects.filter(
                    cart_id=cart, product_id__product_id__id__in=product_ids
                ).values_list('product_id__product_id__id', flat=True)
            except Cart.DoesNotExist:
                return Response(
                    {
                        'success': False,
                        'message': 'Cart not found.',
                        'code': 'not_found',
                        'status': status.HTTP_404_NOT_FOUND,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        # Validate product existence in the campaign
        employee_product_query = EmployeeGroupCampaignProduct.objects.filter(
            employee_group_campaign_id__campaign__code=campaign_code,
            product_id__in=product_ids,
        )

        if not get_employee_admin_preview(employee):
            employee_product_query = employee_product_query.filter(
                employee_group_campaign_id__campaign__status__in=[
                    Campaign.CampaignStatusEnum.ACTIVE.name,
                    Campaign.CampaignStatusEnum.PREVIEW.name,
                ]
            )

        employee_products = employee_product_query.all()
        if not employee_products.exists():
            return Response(
                {
                    'success': False,
                    'message': "Product(s) doesn't exist or not active in the campaign",
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create Share object
        share = Share.objects.create(
            share_type=share_type,
            campaign_code=campaign_code,
            owner=employee,
        )

        # Create ProductShare entries
        for employee_product in employee_products:
            share.products.add(employee_product.product_id)

        return Response(
            {
                'success': True,
                'message': 'Products shared successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    'share_id': share.share_id,
                },
            },
            status=status.HTTP_200_OK,
        )


class GetShareDetailsView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(lang_decorator)
    def get(self, request, share_id):
        try:
            share = Share.objects.get(share_id=share_id)
        except Share.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'message': 'Share not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        response_data = {
            'share_type': share.share_type,
            'products': [],
            'cart': None,
        }

        if share.share_type == ShareTypeEnum.Product.value:
            # Handle the Product share logic
            product_data = []

            # Retrieve all products related to this share
            product_shares = share.products.all()
            campaign_code = share.campaign_code

            employee_product_query = EmployeeGroupCampaignProduct.objects.filter(
                employee_group_campaign_id__campaign__code=campaign_code,
                product_id__in=product_shares,
            )

            if not get_employee_admin_preview(request.user):
                employee_product_query = employee_product_query.filter(
                    employee_group_campaign_id__campaign__status__in=[
                        Campaign.CampaignStatusEnum.ACTIVE.name,
                        Campaign.CampaignStatusEnum.PREVIEW.name,
                    ]
                )

            for employee_product in employee_product_query:
                serializer = ProductSerializerCampaign(
                    employee_product.product_id,
                    context={
                        'campaign': employee_product.employee_group_campaign_id.campaign,  # noqa: E501
                        'employee': employee_product.employee_group_campaign_id.employee_group,  # noqa: E501
                    },
                )
                product_data.append(serializer.data)

            response_data['products'] = product_data
            if employee_product_query.exists():
                first_employee_product = employee_product_query.first()
                response_data['budget_per_employee'] = (
                    first_employee_product.employee_group_campaign_id.budget_per_employee
                )
                response_data['displayed_currency'] = (
                    first_employee_product.employee_group_campaign_id.displayed_currency
                )

        elif share.share_type == ShareTypeEnum.Cart.value:
            try:
                product_shares = share.products.all()
                campaign_code = share.campaign_code

                employee_product_query = EmployeeGroupCampaignProduct.objects.filter(
                    employee_group_campaign_id__campaign__code=campaign_code,
                    product_id__in=product_shares,
                )

                campaign = Campaign.objects.filter(
                    code=campaign_code,
                    status__in=[
                        Campaign.CampaignStatusEnum.ACTIVE.name,
                        Campaign.CampaignStatusEnum.PREVIEW.name,
                    ],
                ).first()
                if not campaign:
                    return Response(
                        {
                            'success': False,
                            'message': 'Campaign not found or inactive.',
                            'code': 'not_found',
                            'status': status.HTTP_404_NOT_FOUND,
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

                employee = share.owner
                campaign_employee = CampaignEmployee.objects.filter(
                    campaign=campaign, employee=employee
                ).first()

                cart = Cart.objects.filter(
                    campaign_employee_id=campaign_employee.id
                ).first()
                serializer = CartSerializer(
                    cart,
                    context={'campaign': campaign, 'employee': employee.employee_group},
                )

                response_data['cart'] = serializer.data
                if employee_product_query.exists():
                    first_employee_product = employee_product_query.first()
                    response_data['budget_per_employee'] = (
                        first_employee_product.employee_group_campaign_id.budget_per_employee
                    )
                    response_data['displayed_currency'] = (
                        first_employee_product.employee_group_campaign_id.displayed_currency
                    )

            except (Cart.DoesNotExist, AttributeError):
                return Response(
                    {
                        'success': False,
                        'message': 'Cart not found.',
                        'code': 'not_found',
                        'status': status.HTTP_404_NOT_FOUND,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(
            {
                'success': True,
                'message': 'Share details fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': response_data,
            },
            status=status.HTTP_200_OK,
        )


class EmployeeView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def get(self, request, organization_id):
        serializer = EmployeeWithGroupSerializer(
            Employee.objects.select_related('employee_group__organization').filter(
                employee_group__organization__pk=organization_id
            ),
            many=True,
        )

        return Response(
            {
                'message': 'employees fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class CampaignProductsView(APIView):
    authentication_classes = [EmployeeAuthentication, AdminPreviewAuthentication]
    permission_classes = [EmployeePermissions]

    @method_decorator(lang_decorator)
    def get(self, request, campaign_code):
        # parse Get data
        request_serializer = CampaignProductsGetSerializer(data=request.GET)

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
        request_category_id = request_serializer.validated_data.get('category_id', None)
        request_q = request_serializer.validated_data.get('q', None)
        request_original_budget = request_serializer.validated_data.get(
            'original_budget'
        )
        request_budget = request_serializer.validated_data.get('budget', None)
        request_sort = request_serializer.validated_data.get('sort', None)
        request_subcategories = request_serializer.validated_data.get(
            'sub_categories', None
        )
        request_brands = request_serializer.validated_data.get('brands', None)
        request_min_price = request_serializer.validated_data.get('min_price', None)
        request_max_price = request_serializer.validated_data.get('max_price', None)
        request_product_type = request_serializer.validated_data.get(
            'product_type', None
        )

        campaign_query = Campaign.objects.filter(code=campaign_code)

        if not get_employee_admin_preview(request.user):
            campaign_query = campaign_query.filter(
                status__in=[
                    Campaign.CampaignStatusEnum.ACTIVE.name,
                    Campaign.CampaignStatusEnum.PREVIEW.name,
                ]
            )

        campaign = campaign_query.first()

        if campaign:
            employee_group_campaign = EmployeeGroupCampaign.objects.filter(
                employee_group=request.user.employee_group,
                campaign=campaign,
            ).first()

        # campaign or employee group campaign not found
        if not campaign or not employee_group_campaign:
            return Response(
                {
                    'success': False,
                    'message': 'Campaign not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        products = filter_campaign_products_with_calculated_price(
            campaign=campaign, employee_group_campaign=employee_group_campaign
        )

        products = products.filter(active=True)

        if request_category_id:
            products = products.filter(product_id__categories__id=request_category_id)

        if request_q:
            products = products.filter(
                Q(product_id__name_en__icontains=request_q)
                | Q(product_id__name_he__icontains=request_q)
            )

        # filter by categories
        if request_subcategories:
            products = products.filter(
                product_id__tags__in=request_subcategories.split(',')
            )

        # filter by brands
        if request_brands:
            products = products.filter(
                product_id__brand__id__in=request_brands.split(',')
            )

        # filter by min price
        if request_min_price:
            products = products.filter(
                Q(calculated_price__gte=request_min_price) | Q(calculated_price=0)
            )

        # filter by max price
        if request_max_price:
            products = products.filter(calculated_price__lte=request_max_price)

        # filter by product type
        if request_product_type:
            products = products.filter(
                product_id__product_kind__in=request_product_type.split(',')
            )
        total_count = products.count()
        # count products before adding the budget filter if one was requested
        in_budget_count = products.filter(
            calculated_price__lte=employee_group_campaign.budget_per_employee
        ).count()

        # TODO: remove original budget. this is now included in the budget
        # parameter and is kept in case some users have loaded and cached
        # client code
        if request_original_budget == 1:
            # filter for products that cost exactly the same as the budget
            products = products.filter(
                calculated_price=employee_group_campaign.budget_per_employee
            )

        if request_budget == 1:
            # filter for products that cost up to and including the budget
            products = products.filter(
                calculated_price__lte=employee_group_campaign.budget_per_employee
            )
        elif request_budget == 2:
            # filter for products that cost exactly the same as the budget
            products = products.filter(
                calculated_price=employee_group_campaign.budget_per_employee
            )
        elif request_budget == 3:
            # filter for products that cost more than the budget
            products = products.filter(
                calculated_price__gt=employee_group_campaign.budget_per_employee
            )

        # a paginated query *must* have a definitive order_by
        order = 'calculated_price'
        if request_sort and request_sort == 'desc':
            order = '-calculated_price'
        products = products.order_by(order, 'product_id_id')

        paginator = Paginator(products, request_limit)
        page = paginator.get_page(request_page)

        products_serializer = ProductSerializerCampaign(
            [egcp.product_id for egcp in page.object_list],
            many=True,
            context={'campaign': campaign, 'employee': request.user.employee_group},
        )

        return Response(
            {
                'success': True,
                'message': 'products fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    'page_data': products_serializer.data,
                    'page_num': page.number,
                    'has_more': page.has_next(),
                    'total_count': total_count,
                    'in_budget_count': in_budget_count,
                },
            },
            status=status.HTTP_200_OK,
        )


class EmployeeLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, campaign_code):
        try:
            campaign = Campaign.objects.filter(code=campaign_code).first()
            if (
                not campaign
                or campaign.status != Campaign.CampaignStatusEnum.ACTIVE.name
            ):
                return Response(
                    {
                        'success': False,
                        'message': 'Bad credentials',
                        'code': 'bad_credentials',
                        'status': status.HTTP_401_UNAUTHORIZED,
                        'data': {},
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            serializer = EmployeeLoginSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Request is invalid.',
                        'code': 'request_invalid',
                        'status': status.HTTP_400_BAD_REQUEST,
                        'data': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            request = serializer.validated_data

            otp = request.pop('otp', None)

            if 'email' in request:
                request['email'] = request['email'].lower()

            # Step 1: Build the identifier (email, phone_number or auth_id)
            identifier = {}
            if 'email' in request:
                identifier['email'] = request['email']
            elif 'phone_number' in request:
                identifier['phone_number'] = request['phone_number']
            elif 'auth_id' in request:
                identifier['auth_id'] = request['auth_id']

            # Step 2: Check if user is registered in the system at all
            if not Employee.objects.filter(**identifier).exists():
                return Response(
                    {
                        'success': False,
                        'message': 'The details you entered are incorrect, check the details and re-enter',  # noqa: E501
                        'code': 'user_not_registered',
                        'status': status.HTTP_401_UNAUTHORIZED,
                        'data': {},
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # Convert email to lowercase before comparing
            if 'email' in request:
                request['email'] = request['email'].lower()

            employee = campaign.employees.filter(
                **request, campaign=campaign, active=True
            ).first()
            if not employee:
                return Response(
                    {
                        'success': False,
                        'message': 'Bad credentials',
                        'code': 'bad_credentials',
                        'status': status.HTTP_401_UNAUTHORIZED,
                        'data': {},
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            egc = EmployeeGroupCampaign.objects.filter(
                campaign=campaign, employee_group=employee.employee_group
            ).first()
            if not egc:
                return Response(
                    {
                        'success': False,
                        'message': 'Bad credentials',
                        'code': 'bad_credentials',
                        'status': status.HTTP_401_UNAUTHORIZED,
                        'data': {},
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            egc_auth_map = {
                'EMAIL': 'email',
                'SMS': 'phone_number',
                'AUTH_ID': 'auth_id',
                'VOUCHER_CODE': 'auth_id',
            }
            if not (
                (employee.login_type in egc_auth_map.keys())
                and (egc_auth_map[employee.login_type] in request.keys())
            ):
                return Response(
                    {
                        'success': False,
                        'message': 'Bad credentials',
                        'code': 'bad_credentials',
                        'status': status.HTTP_401_UNAUTHORIZED,
                        'data': {},
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            if (
                'auth_id' in request.keys()
                and egc_auth_map[employee.login_type] == 'auth_id'
            ):
                # auth_id authorization groups need no otp
                auth_token = jwt_encode({'employee_id': employee.pk})
                self.update_last_login(campaign=campaign, employee=employee)

                return Response(
                    {
                        'success': True,
                        'message': 'User logged in successfully',
                        'status': status.HTTP_200_OK,
                        'data': {
                            'first_name': employee.first_name,
                            'last_name': employee.last_name,
                            'email': employee.email,
                            'auth_token': auth_token,
                        },
                    },
                    status=status.HTTP_200_OK,
                )
            elif otp:
                if employee.verify_otp(otp):
                    # otp was provided and successfuly validated
                    auth_token = jwt_encode({'employee_id': employee.pk})
                    self.update_last_login(campaign=campaign, employee=employee)

                    return Response(
                        {
                            'success': True,
                            'message': 'User logged in successfully',
                            'status': status.HTTP_200_OK,
                            'data': {
                                'first_name': employee.first_name,
                                'last_name': employee.last_name,
                                'email': employee.email,
                                'auth_token': auth_token,
                            },
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    # otp was provided and could not be validated
                    return Response(
                        {
                            'success': False,
                            'code': 'bad_otp',
                            'message': 'Bad OTP code',
                            'status': status.HTTP_401_UNAUTHORIZED,
                            'data': {},
                        },
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

            if employee.login_type == 'EMAIL':
                send_otp_token_email(
                    email=employee.email, otp_token=employee.generate_otp()
                )

            if employee.login_type == 'SMS':
                send_otp_token_sms(
                    phone_number=employee.phone_number,
                    otp_token=employee.generate_otp(),
                )

            return Response(
                {
                    'success': False,
                    'code': 'missing_otp',
                    'message': 'Missing OTP code',
                    'status': status.HTTP_401_UNAUTHORIZED,
                    'data': {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as ex:
            logger.error(f'Employee login error: {str(ex)}')
            return Response(
                {
                    'success': False,
                    'message': 'Unknown error occured',
                    'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                    'data': {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @classmethod
    def update_last_login(cls, campaign: Campaign, employee: Employee):
        campaign_employee: CampaignEmployee = CampaignEmployee.objects.filter(
            campaign=campaign, employee=employee
        ).first()
        if campaign_employee:
            campaign_employee.last_login = datetime.now()
            campaign_employee.save(update_fields=['last_login'])


class OrderDetailsView(APIView):
    authentication_classes = [EmployeeAuthentication]
    permission_classes = [EmployeePermissions]

    @method_decorator(lang_decorator)
    def get(self, request, campaign_code):
        campaign_employee = CampaignEmployee.objects.filter(
            employee=request.user,
            campaign__code=campaign_code,
            campaign__status__in=[
                Campaign.CampaignStatusEnum.ACTIVE.name,
                Campaign.CampaignStatusEnum.PREVIEW.name,
            ],
        ).first()

        if campaign_employee:
            order = Order.objects.filter(
                campaign_employee_id=campaign_employee,
                status=Order.OrderStatusEnum.PENDING.name,
            ).first()

        if not campaign_employee or not order:
            return Response(
                {
                    'success': False,
                    'message': 'Order not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        order_serializer = OrderSerializer(
            order,
            context={
                'campaign': campaign_employee.campaign,
                'employee': request.user.employee_group,
            },
        )

        return Response(
            {
                'success': True,
                'message': 'Employee order fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': order_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class CancelOrderView(APIView):
    authentication_classes = [EmployeeAuthentication]
    permission_classes = [EmployeePermissions]

    def put(self, request, campaign_code, order_id):
        order = Order.objects.filter(
            pk=order_id,
            campaign_employee_id__campaign__code=campaign_code,
            campaign_employee_id__campaign__status__in=[
                Campaign.CampaignStatusEnum.ACTIVE.name,
                Campaign.CampaignStatusEnum.PREVIEW.name,
            ],
            campaign_employee_id__employee=request.user,
        ).first()

        # order not found
        if not order:
            return Response(
                {
                    'success': False,
                    'message': 'Order not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        elif order.cost_added > 0:
            return Response(
                {
                    'success': False,
                    'message': 'Cannot cancel paid order.',
                    'code': 'order_paid',
                    'status': status.HTTP_402_PAYMENT_REQUIRED,
                    'data': {},
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        elif order.status == Order.OrderStatusEnum.CANCELLED.name:
            return Response(
                {
                    'success': False,
                    'message': 'Order is already cancelled.',
                    'code': 'order_already_cancelled',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # cancel the order
        order.status = Order.OrderStatusEnum.CANCELLED.name
        order.save()
        CartProduct.objects.filter(
            product_id__in=order.orderproduct_set.all().values_list(
                'product_id', flat=True
            ),
            cart_id__campaign_employee_id__employee=request.user,
            cart_id__campaign_employee_id__campaign__code=campaign_code,
            cart_id__campaign_employee_id__campaign__status__in=[
                Campaign.CampaignStatusEnum.ACTIVE.name,
                Campaign.CampaignStatusEnum.PREVIEW.name,
            ],
        ).delete()

        return Response(
            {
                'success': True,
                'message': 'order canceled successfully.',
                'status': status.HTTP_200_OK,
                'data': {},
            },
            status=status.HTTP_200_OK,
        )


class CategoriesBrandsSuppliersTagsView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def get(self, request):
        serializer_suppliers = SupplierSerializer(Supplier.objects.all(), many=True)
        serializer_categories = CategorySerializer(Category.objects.all(), many=True)
        serializer_tags = TagSerializer(Tag.objects.all(), many=True)
        serializer_brands = BrandSerializer(Brand.objects.all(), many=True)
        return Response(
            {
                'success': True,
                'message': 'categories suppliers tags fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    'suppliers': serializer_suppliers.data,
                    'categories': serializer_categories.data,
                    'tags': serializer_tags.data,
                    'brands': serializer_brands.data,
                },
            },
            status=status.HTTP_200_OK,
        )


class EmployeeOrderView(APIView):
    authentication_classes = [EmployeeAuthentication]
    permission_classes = [EmployeePermissions]

    def post(self, request, campaign_code):
        employee = request.user

        campaign = Campaign.objects.filter(
            code=campaign_code,
            employees=employee,
            status__in=[
                Campaign.CampaignStatusEnum.ACTIVE.name,
                Campaign.CampaignStatusEnum.PREVIEW.name,
            ],
        ).first()
        employee_group_campaign = None
        if campaign:
            employee_group_campaign = EmployeeGroupCampaign.objects.filter(
                campaign=campaign, employee_group=employee.employee_group
            ).first()

        if not campaign or not employee_group_campaign:
            return Response(
                {
                    'success': False,
                    'message': 'Bad credentials',
                    'code': 'bad_credentials',
                    'status': status.HTTP_401_UNAUTHORIZED,
                    'data': {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        cart = Cart.objects.filter(
            campaign_employee_id__campaign=campaign,
            campaign_employee_id__employee=employee,
        ).first()

        if not cart:
            return Response(
                {
                    'success': False,
                    'message': 'Cart not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        cart_products = CartProduct.objects.filter(
            cart_id=cart,
        ).select_related('product_id')

        if len(cart_products) == 0:
            return Response(
                {
                    'success': False,
                    'message': 'Empty cart.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        products_kind = [
            cart_product.product_id.product_id.product_kind
            for cart_product in cart_products
        ]

        money_kind = [
            kind for kind in products_kind if kind == Product.ProductKindEnum.MONEY.name
        ]

        request_data = EmployeeOrderRequestSerializer(
            data=request.data,
            context={
                'delivery_location': (
                    employee_group_campaign.employee_group.delivery_location
                ),
                'checkout_location': (employee_group_campaign.check_out_location),
                'lang': request.GET.get('lang', 'en'),
                'one_money_product': len(money_kind) > 0,
                'all_money_product': len(products_kind) == len(money_kind),
            },
        )

        if not request_data.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_data.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_order_data = request_data.validated_data

        # check if all the products are available
        for cart_product in cart_products:
            product_quantity = cart_product.product_id.product_id.product_quantity
            if product_quantity < cart_product.quantity:
                cart_product.quantity = product_quantity
                cart_product.save(update_fields=['quantity'])
                return Response(
                    {
                        'success': False,
                        'message': gettext(
                            (
                                'The requested quantity is not available. '
                                'The remaining quantity is %(remaining_quantity)d.'
                            )
                        )
                        % {'remaining_quantity': product_quantity},
                        'code': 'request_invalid',
                        'status': status.HTTP_400_BAD_REQUEST,
                        'data': request_data.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        campaign_employee = CampaignEmployee.objects.filter(
            campaign=campaign, employee=employee
        ).first()
        if campaign.campaign_type == Campaign.CampaignTypeEnum.NORMAL.name:
            # check if there is already a pending order, and if so fail
            existing_order = Order.objects.filter(
                campaign_employee_id=campaign_employee,
                status=Order.OrderStatusEnum.PENDING.name,
            ).first()

            if existing_order:
                return Response(
                    {
                        'success': False,
                        'message': 'Employee already ordered.',
                        'code': 'already_ordered',
                        'status': status.HTTP_400_BAD_REQUEST,
                        'data': {},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        employee_order = Order.objects.create(
            **request_order_data,
            campaign_employee_id=campaign_employee,
            order_date_time=datetime.now(timezone.utc),
            cost_from_budget=0,
            cost_added=0,
            status=Order.OrderStatusEnum.INCOMPLETE.name,
            # this will return None if there is no active impersonation,
            # and will return the impersonating admin user if this is an
            # impersonated session
            impersonated_by_id=get_employee_impersonated_by(request.user),
        )

        order_price = 0

        # used for products data payment
        products_payment = {}
        payment_description = []

        for idx, cart_product in enumerate(cart_products):
            products = [
                cart_product.product_id,
            ]

            for idx_1, product in enumerate(products):
                employee_group_campaign_product = product
                product_price = 0
                quantity = cart_product.quantity
                if product.product_id.product_kind != 'MONEY':
                    organization_product = OrganizationProduct.objects.filter(
                        organization=employee.employee_group.organization,
                        product=employee_group_campaign_product.product_id,
                    ).first()
                    if organization_product and organization_product.price:
                        product_price = organization_product.price
                    else:
                        product_price = (
                            employee_group_campaign_product.product_id.sale_price
                        )
                else:
                    egcp = EmployeeGroupCampaignProduct
                    product: egcp = egcp.objects.get(
                        employee_group_campaign_id__campaign=campaign,
                        employee_group_campaign_id__employee_group=employee.employee_group,
                        product_id=product.product_id,
                    )

                    if product:
                        budget = (
                            product.employee_group_campaign_id.budget_per_employee or 0
                        )
                        product_price = budget

                order_price += (product_price if product_price else 0) * quantity

                products_payment[f'productData[{str(idx + idx_1)}][quantity]'] = (
                    quantity
                )
                products_payment[f'productData[{str(idx + idx_1)}][catalog_number]'] = (
                    employee_group_campaign_product.product_id.sku
                )

                payment_description.append(
                    f'{employee_group_campaign_product.product_id.name} x {quantity}'
                )
                variations = cart_product.variations
                lang = request.GET.get('lang', 'en')
                if variations and lang == 'he':
                    variations = transform_variations(variations, mode='request')
                voucher_val = self.calculate_voucher_val(
                    employee_group_campaign_product
                )
                OrderProduct.objects.create(
                    order_id=employee_order,
                    product_id=employee_group_campaign_product,
                    quantity=quantity,
                    variations=variations,
                    voucher_val=voucher_val,
                )

        total_budget = (
            campaign_employee.total_budget if campaign_employee.total_budget else 0
        )
        left_budget = total_budget - employee.used_budget_campaign(campaign=campaign)
        amount_to_be_payed = order_price - left_budget

        if (
            amount_to_be_payed > 0
            and employee_group_campaign.check_out_location
            == EmployeeGroupCampaign.CheckoutLocationTypeEnum.GLOBAL.name
        ):
            return Response(
                {
                    'success': False,
                    'message': f'Payment can not added in checkout location '
                    f'"{EmployeeGroupCampaign.CheckoutLocationTypeEnum.GLOBAL.name}"',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        employee_order.cost_from_budget = (
            left_budget if amount_to_be_payed > 0 else order_price
        )
        employee_order.cost_added = amount_to_be_payed if amount_to_be_payed > 0 else 0

        details = []
        details.append(f'Order ID: {employee_order.reference}')
        details.append(f'Order Date: {employee_order.order_date_time}')
        details.append(f'Employee Name: {employee_order.full_name}')
        details.append('Products:')
        for cart_product in cart_products:
            product = cart_product.product_id.product_id
            details.append(
                f' - {product.name}'
                f' (SKU: {product.sku})'
                f' X Quantity: {cart_product.quantity}'
            )
        details.append(f'Cost Added: {employee_order.cost_added}')
        details.append(f'Cost from Budget: {employee_order.cost_from_budget}')
        details.append(
            f'Total cost: {employee_order.cost_added + employee_order.cost_from_budget}'
        )
        employee_order.raw_details = '\n'.join(details)
        employee_order.save(
            update_fields=['cost_from_budget', 'cost_added', 'raw_details']
        )

        if amount_to_be_payed > 0:
            payer_full_name = request_order_data.get('full_name', None)
            payer_phone_number = request_order_data.get('phone_number', None)
            print(amount_to_be_payed)

            payment_auth_code = initiate_payment(
                employee_order,
                amount_to_be_payed,
                payer_full_name,
                payer_phone_number,
                products_payment,
                f'Invoice {str(employee_order.pk)}',
                'en',  # lang,
                ', '.join(payment_description),
            )

            if not payment_auth_code:
                logger.error(
                    f'Failed to initiate payment for employee {request.user.id}'
                )
                raise Exception('failed to initiate payment')

            # return payment link to client
            return Response(
                {
                    'success': False,
                    'message': 'Order payment required.',
                    'status': status.HTTP_402_PAYMENT_REQUIRED,
                    'data': {
                        'payment_code': payment_auth_code,
                    },
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        else:
            employee_order.status = employee_order.OrderStatusEnum.PENDING.name
            employee_order.save(update_fields=['status'])

            # Decrease the actual product quantity
            if employee_order.status in [
                employee_order.OrderStatusEnum.PENDING.name,
                employee_order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
            ]:
                for cart_product in cart_products:
                    product = cart_product.product_id.product_id
                    product.product_quantity -= cart_product.quantity
                    product.save(update_fields=['product_quantity'])

            if campaign.campaign_type == 'WALLET':
                cart_products.delete()

            send_order_confirmation_email(employee_order)

        return Response(
            {
                'success': True,
                'message': 'Order placed successfully.',
                'status': status.HTTP_200_OK,
                'data': {'reference': employee_order.reference},
            },
            status=status.HTTP_200_OK,
        )

    def calculate_voucher_val(self, egc_product: EmployeeGroupCampaignProduct):
        budget = egc_product.employee_group_campaign_id.budget_per_employee
        if budget is None or egc_product.product_id.product_kind != 'MONEY':
            return None

        if egc_product.discount_mode == 'EMPLOYEE':
            discount_rate = egc_product.organization_discount_rate or 0
            return round(budget / (1 - (discount_rate / 100)), 1)
        return round(budget, 1)


class GetCampaignView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def get(self, request, employee_group_id):
        try:
            employee_group = EmployeeGroup.objects.get(id=employee_group_id)
            return Response(
                {
                    'success': True,
                    'message': 'Campaign names have been fetched successfully.',
                    'status': status.HTTP_200_OK,
                    'data': employee_group.campaign_names,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as ex:
            logger.exception(
                f'An error occured while fetching the campaigns: {str(ex)}'
            )
            return Response(
                {
                    'success': False,
                    'message': 'Employee Group does not exist',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )


class CartAddProductView(APIView):
    authentication_classes = [EmployeeAuthentication]
    permission_classes = [EmployeePermissions]

    def handle_cart(
        self,
        campaign_employee: CampaignEmployee,
        employee_group_campaign: EmployeeGroupCampaign,
        employee_group_campaign_product: EmployeeGroupCampaignProduct,
        quantity: int,
        lang: str,
        variations: dict = None,
    ) -> Cart:
        cart, _ = Cart.objects.get_or_create(campaign_employee_id=campaign_employee)

        multi_selection = (
            employee_group_campaign.product_selection_mode
            == EmployeeGroupCampaign.ProductSelectionTypeEnum.MULTIPLE.name
        )
        if variations and lang == 'he':
            variations = transform_variations(variations, mode='request')

        if multi_selection:
            if variations:
                existing_cart_product = CartProduct.objects.filter(
                    cart_id=cart,
                    product_id=employee_group_campaign_product,
                    variations=variations,
                ).first()
            else:
                existing_cart_product = CartProduct.objects.filter(
                    cart_id=cart, product_id=employee_group_campaign_product
                ).first()
            if existing_cart_product:
                if quantity == 0:
                    existing_cart_product.delete()
                else:
                    existing_cart_product.quantity = quantity
                    existing_cart_product.variations = variations
                    existing_cart_product.save(update_fields=['quantity', 'variations'])
            else:
                if quantity > 0:
                    new_cart_product = CartProduct(
                        cart_id=cart,
                        product_id=employee_group_campaign_product,
                        quantity=quantity,
                        variations=variations,
                    )
                    new_cart_product.save()
        else:
            # clear cart for single selection - we will create the one new cart
            # product
            CartProduct.objects.filter(cart_id=cart).delete()

            if quantity > 0:
                new_cart_product = CartProduct(
                    cart_id=cart,
                    product_id=employee_group_campaign_product,
                    quantity=quantity,
                    variations=variations,
                )
                new_cart_product.save()

        return cart

    def post(self, request, campaign_code):
        request_serializer = CartAddProductSerializer(data=request.data)
        if not request_serializer.is_valid() and not (
            'quantity' in request_serializer.errors
            and len(request_serializer.errors) == 1
        ):
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

        if (
            'quantity' in request_serializer.errors
            and len(request_serializer.errors) == 1
        ):
            product_id = request.data.get('product_id')
            product = Product.objects.filter(id=product_id).first()
            quantity = product.product_quantity
            variations = request.data.get('variations')
        else:
            product_id = request_serializer.validated_data.get('product_id')
            quantity = request_serializer.validated_data.get('quantity')
            variations = request_serializer.validated_data.get('variations')

        campaign = Campaign.objects.filter(
            code=campaign_code,
            status__in=[
                Campaign.CampaignStatusEnum.ACTIVE.name,
                Campaign.CampaignStatusEnum.PREVIEW.name,
            ],
        ).first()

        employee = request.user
        employee_group = employee.employee_group

        campaign_employee = CampaignEmployee.objects.filter(
            campaign=campaign, employee=employee
        ).first()

        employee_group_campaign = EmployeeGroupCampaign.objects.filter(
            employee_group=employee_group, campaign=campaign
        ).first()
        employee_group_campaign_product = EmployeeGroupCampaignProduct.objects.filter(
            product_id_id=product_id, employee_group_campaign_id=employee_group_campaign
        ).first()

        if not campaign_employee or not employee_group_campaign_product:
            return Response(
                {
                    'success': False,
                    'message': 'Bad credentials',
                    'code': 'bad_credentials',
                    'status': status.HTTP_401_UNAUTHORIZED,
                    'data': {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        cart = self.handle_cart(
            campaign_employee,
            employee_group_campaign,
            employee_group_campaign_product,
            quantity,
            request.GET.get('lang', 'en'),
            variations,
        )

        if (
            'quantity' in request_serializer.errors
            and len(request_serializer.errors) == 1
        ):
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

        return Response(
            {
                'success': True,
                'message': 'Cart updated successfully.',
                'status': status.HTTP_200_OK,
                'data': {'cart_id': cart.pk},
            },
            status=status.HTTP_200_OK,
        )


class CampaignImpersonationTokenExhcangeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, campaign_code):
        request_data = CampaignExchangeRequestSerializer(data=request.data)

        if not request_data.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_token = request_data.validated_data['t']

        impersonation_token = CampaignImpersonationToken.objects.filter(
            token=request_token,
            campaign__code=campaign_code,
            valid_until_epoch_seconds__gte=int(time()),
            used=False,
        ).first()

        if not impersonation_token:
            return Response(
                {
                    'success': False,
                    'message': 'Not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        token_payload = {
            'admin_id': impersonation_token.user.id,
            'campaign_id': impersonation_token.campaign_id,
        }

        # if we are impersonating a specific employee add their id to the
        # token, otherwise this is an admin preview
        if impersonation_token.campaign_employee:
            token_payload['impersonated_employee_id'] = (
                impersonation_token.campaign_employee.id
            )
        elif impersonation_token.employee_group_campaign_id:
            token_payload['admin_preview'] = True
            token_payload['employee_group_campaign_id'] = (
                impersonation_token.employee_group_campaign_id
            )
        else:
            logger.error(
                'Attempted to use token with no campaign employee nor employee '
                f'group campaign. Token id: {impersonation_token.pk}'
            )
            return Response(
                {
                    'success': False,
                    'message': 'Server error.',
                    'code': 'server_error',
                    'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                    'data': {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        auth_token = jwt_encode(token_payload)

        impersonation_token.used = True
        impersonation_token.save(update_fields=['used'])

        return Response(
            {
                'success': True,
                'message': 'Token exchanged successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    'auth_token': auth_token,
                },
            },
            status=status.HTTP_200_OK,
        )


class GetCartProductsView(APIView):
    authentication_classes = [EmployeeAuthentication]
    permission_classes = [EmployeePermissions]

    @method_decorator(lang_decorator)
    def get(self, request, campaign_code):
        campaign = Campaign.objects.filter(
            code=campaign_code,
            status__in=[
                Campaign.CampaignStatusEnum.ACTIVE.name,
                Campaign.CampaignStatusEnum.PREVIEW.name,
            ],
        ).first()

        employee = request.user

        campaign_employee = CampaignEmployee.objects.filter(
            campaign=campaign, employee=employee
        ).first()

        try:
            cart = Cart.objects.get(campaign_employee_id=campaign_employee)
        except Exception:
            return Response(
                {
                    'success': False,
                    'message': 'Not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CartSerializer(
            cart,
            context={
                'campaign': campaign,
                'employee': request.user.employee_group,
                'lang': request.GET.get('lang', 'en'),
            },
        )

        return Response(
            {
                'success': True,
                'message': 'Cart fetched successfully',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class FilterLookupView(APIView):
    authentication_classes = [EmployeeAuthentication, QuickOfferAuthentication]
    permission_classes = [EmployeeOrQuickOfferPermission]

    @method_decorator(lang_decorator)
    def get(self, request, campaign_code):
        request_serializer = FilterLookupSerializer(data=request.GET)

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

        request_lookup = request_serializer.validated_data['lookup']
        request_q = request_serializer.validated_data.get('q', None)
        category = request_serializer.validated_data.get('category')
        request_sub_categories = request_serializer.validated_data.get('sub_categories')
        request_product_kinds = request_serializer.validated_data.get('product_kinds')
        request_brands = request_serializer.validated_data.get('brands')
        including_tax = request_serializer.validated_data.get('including_tax', True)

        employee_group_campaign = None

        if request.user:
            employee_group_campaign_query = (
                EmployeeGroupCampaign.objects.select_related('campaign').filter(
                    campaign__code=campaign_code,
                    employee_group__pk=request.user.employee_group_id,
                )
            )

            if not get_employee_admin_preview(request.user):
                employee_group_campaign_query = employee_group_campaign_query.filter(
                    campaign__status__in=[
                        Campaign.CampaignStatusEnum.ACTIVE.name,
                        Campaign.CampaignStatusEnum.PREVIEW.name,
                    ]
                )

            employee_group_campaign = employee_group_campaign_query.first()

            if not employee_group_campaign:
                return Response(
                    {
                        'success': False,
                        'message': 'Campaign not found.',
                        'code': 'not_found',
                        'status': status.HTTP_404_NOT_FOUND,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            campaign = Campaign.objects.filter(code=campaign_code).first()
            campaign_products = (
                EmployeeGroupCampaignProduct.objects.filter(
                    employee_group_campaign_id=employee_group_campaign.id,
                    product_id__active=True,
                )
                .select_related('product_id')
                .annotate(
                    calculated_price=Coalesce(
                        Subquery(
                            OrganizationProduct.objects.filter(
                                organization=campaign.organization,
                                product=OuterRef('product_id'),
                            )
                            .annotate(
                                org_price=Case(
                                    When(price__gt=0, then='price'),
                                    default=None,
                                    output_field=DecimalField(),
                                )
                            )
                            .values('org_price')[:1],  # subquery output
                        ),
                        'product_id__sale_price',
                        output_field=DecimalField(),
                    )
                )
            )
            if category:
                campaign_products = campaign_products.filter(
                    product_id__categories__id=category
                )
            if request_product_kinds:
                campaign_products = campaign_products.filter(
                    product_id__product_kind__in=request_product_kinds.split(',')
                )
            if request_sub_categories:
                campaign_products = campaign_products.filter(
                    product_id__tags__in=request_sub_categories.split(',')
                )
            if request_brands:
                campaign_products = campaign_products.filter(
                    product_id__brand__id__in=request_brands.split(',')
                )
            request_budget = request_serializer.validated_data.get('budget')
            if request_budget == 1:
                # filter for products that cost up to and including the budget
                campaign_products = campaign_products.filter(
                    calculated_price__lte=employee_group_campaign.budget_per_employee
                )
            elif request_budget == 2:
                # filter for products that cost exactly the same as the budget
                campaign_products = campaign_products.filter(
                    calculated_price=employee_group_campaign.budget_per_employee
                )
            elif request_budget == 3:
                # filter for products that cost more than the budget
                campaign_products = campaign_products.filter(
                    Q(calculated_price__gte=employee_group_campaign.budget_per_employee)
                    | Q(calculated_price=0)
                )

            if request_q:
                campaign_products = campaign_products.filter(
                    Q(product_id__name_en__icontains=request_q)
                    | Q(product_id__name_he__icontains=request_q)
                )

            product_ids = [product.product_id_id for product in campaign_products]
            campaign_or_quick_offer = employee_group_campaign.campaign
        else:
            quick_offer_products = request.quick_offer.products.filter(active=True)
            if category:
                quick_offer_products = quick_offer_products.filter(
                    categories__id=category
                )
            if request_q:
                quick_offer_products = quick_offer_products.filter(
                    Q(name_en__icontains=request_q) | Q(name_he__icontains=request_q)
                )
            product_ids = quick_offer_products.values_list('id', flat=True)
            campaign_or_quick_offer = request.quick_offer

        serialized_data = None
        success_msg = None
        if request_lookup == 'product_kinds':
            success_msg = 'Product kinds fetched successfully.'
            data = get_campaign_product_kinds(product_ids)
            serialized_data = FilterLookupProductKindsSerializer(data, many=True).data
        elif request_lookup == 'brands':
            success_msg = 'Brands fetched successfully.'
            data = get_campaign_brands(product_ids)
            serialized_data = FilterLookupBrandsSerializer(data, many=True).data
        elif request_lookup == 'sub_categories':
            success_msg = 'Sub categories fetched successfully.'
            data = get_campaign_tags(product_ids)
            serialized_data = FilterLookupTagsSerializer(data, many=True).data
        elif request_lookup == 'max_price':
            success_msg = 'Max price fetched successfully.'
            if isinstance(campaign_or_quick_offer, Campaign):
                serialized_data = get_campaign_max_product_price(
                    product_ids=product_ids,
                    campaign=campaign_or_quick_offer,
                    employee_group_campaign=employee_group_campaign,
                )
            else:
                serialized_data = get_quick_offer_max_product_price(
                    product_ids=product_ids,
                    quick_offer=campaign_or_quick_offer,
                    tax_percent=settings.TAX_PERCENT if not including_tax else 0,
                )

        return Response(
            {
                'success': True,
                'message': success_msg,
                'status': status.HTTP_200_OK,
                'data': serialized_data,
            },
            status=status.HTTP_200_OK,
        )


class OrganizationQuickOfferView(APIView):
    authentication_classes = [QuickOfferAuthentication]
    permission_classes = [AllowAny]

    @method_decorator(lang_decorator)
    def get(self, request, quick_offer_code):
        quick_offer_data = QuickOffer.objects.filter(code=quick_offer_code).first()
        if (
            not getattr(request.user, 'is_anonymous', False)
            and request.quick_offer.code == quick_offer_code
        ):
            serializer = QuickOfferSerializer(request.quick_offer)

        else:
            serializer = QuickOfferReadOnlySerializer(quick_offer_data)

        return Response(
            {
                'success': True,
                'message': 'Offers fetched successfully',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class UpdateOrganizationQuickOfferView(APIView):
    authentication_classes = [QuickOfferAuthentication]
    permission_classes = [QuickOfferPermissions]

    @method_decorator(lang_decorator)
    def put(self, request):
        quick_offer: QuickOffer = request.quick_offer

        request_serializer = QuickOfferUpdateSendMyOrderSerializer(data=request.data)
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

        quick_offer.send_my_list = request_serializer.validated_data.get('send_my_list')
        quick_offer.save()

        return Response(
            {
                'success': True,
                'message': 'List sent successfully.',
                'status': status.HTTP_200_OK,
                'data': request_serializer.validated_data,
            },
            status=status.HTTP_200_OK,
        )


class OrganizationQuickOfferLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, quick_offer_code):
        try:
            quick_offer = QuickOffer.objects.filter(code=quick_offer_code).first()
            if (
                not quick_offer
                or quick_offer.status != QuickOffer.StatusEnum.ACTIVE.name
            ):
                return Response(
                    {
                        'success': False,
                        'message': 'Bad credentials',
                        'code': 'bad_credentials',
                        'status': status.HTTP_401_UNAUTHORIZED,
                        'data': {},
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            serializer = OrganizationLoginSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Request is invalid.',
                        'code': 'request_invalid',
                        'status': status.HTTP_400_BAD_REQUEST,
                        'data': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            request = serializer.validated_data
            request_auth_id = request.get('auth_id')
            request_otp = request.get('otp')

            if quick_offer.auth_method == QuickOffer.AuthMethodEnum.AUTH_ID.name:
                if request_auth_id == quick_offer.auth_id:
                    quick_offer.last_login = datetime.now()
                    quick_offer.save(update_fields=['last_login'])
                    return Response(
                        {
                            'success': True,
                            'message': 'Organization logged in successfully',
                            'status': status.HTTP_200_OK,
                            'data': {
                                'auth_token': jwt_encode(
                                    {'quick_offer_id': quick_offer.id}
                                ),
                            },
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {
                            'success': False,
                            'message': 'Bad credentials',
                            'code': 'bad_credentials',
                            'status': status.HTTP_401_UNAUTHORIZED,
                            'data': {},
                        },
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

            if (
                quick_offer.auth_method == QuickOffer.AuthMethodEnum.EMAIL.name
                or quick_offer.auth_method
                == QuickOffer.AuthMethodEnum.PHONE_NUMBER.name
            ):
                if request_otp:
                    if quick_offer.verify_otp(request_otp):
                        quick_offer.last_login = datetime.now()
                        quick_offer.save(update_fields=['last_login'])
                        return Response(
                            {
                                'success': True,
                                'message': 'Organization logged in successfully',
                                'status': status.HTTP_200_OK,
                                'data': {
                                    'auth_token': jwt_encode(
                                        {'quick_offer_id': quick_offer.id}
                                    ),
                                },
                            },
                            status=status.HTTP_200_OK,
                        )
                    else:
                        return Response(
                            {
                                'success': False,
                                'message': 'Bad credentials',
                                'code': 'bad_credentials',
                                'status': status.HTTP_401_UNAUTHORIZED,
                                'data': {},
                            },
                            status=status.HTTP_401_UNAUTHORIZED,
                        )

                if quick_offer.auth_method == QuickOffer.AuthMethodEnum.EMAIL.name:
                    send_otp_token_email(
                        email=quick_offer.email, otp_token=quick_offer.generate_otp()
                    )

                if (
                    quick_offer.auth_method
                    == QuickOffer.AuthMethodEnum.PHONE_NUMBER.name
                ):
                    send_otp_token_sms(
                        phone_number=quick_offer.phone_number,
                        otp_token=quick_offer.generate_otp(),
                    )

                return Response(
                    {
                        'success': False,
                        'code': 'missing_otp',
                        'message': 'Missing OTP code',
                        'status': status.HTTP_401_UNAUTHORIZED,
                        'data': {},
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            return Response(
                {
                    'success': False,
                    'message': 'Bad credentials',
                    'code': 'bad_credentials',
                    'status': status.HTTP_401_UNAUTHORIZED,
                    'data': {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as ex:
            logger.error(f'Organization login error: {str(ex)}')
            return Response(
                {
                    'success': False,
                    'message': 'Unknown error occured',
                    'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                    'data': {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ValidateCodeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, code):
        campaign = Campaign.objects.filter(code=code).exists()

        if campaign:
            return Response(
                {
                    'success': True,
                    'message': 'Campaign code exists',
                    'status': status.HTTP_200_OK,
                    'data': 'campaign_code',
                },
                status=status.HTTP_200_OK,
            )

        quick_offer = QuickOffer.objects.filter(code=code).exists()

        if quick_offer:
            return Response(
                {
                    'success': True,
                    'message': 'Quick offer code exists',
                    'status': status.HTTP_200_OK,
                    'data': 'quick_offer_code',
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                'success': False,
                'message': 'Invalid Code',
                'status': status.HTTP_400_BAD_REQUEST,
                'data': 'invalid_code',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class QuickOfferProductsView(APIView):
    authentication_classes = [QuickOfferAuthentication]
    permission_classes = [QuickOfferPermissions]

    @method_decorator(lang_decorator)
    def get(self, request):
        quick_offer: QuickOffer = request.quick_offer

        request_serializer = QuickOfferProductsRequestSerializer(data=request.GET)
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
        request_category_id = request_serializer.validated_data.get('category_id', None)
        request_q = request_serializer.validated_data.get('q', None)
        request_sort = request_serializer.validated_data.get('sort', None)
        request_subcategories = request_serializer.validated_data.get(
            'sub_categories', None
        )
        request_brands = request_serializer.validated_data.get('brands', None)
        request_min_price = request_serializer.validated_data.get('min_price', None)
        request_max_price = request_serializer.validated_data.get('max_price', None)
        request_product_type = request_serializer.validated_data.get(
            'product_type', None
        )

        request_including_tax = request_serializer.validated_data.get(
            'including_tax', True
        )

        products = quick_offer.products.annotate(
            calculated_price=Coalesce(
                Subquery(
                    OrganizationProduct.objects.filter(
                        organization=request.quick_offer.organization,
                        product=OuterRef('id'),
                    )
                    .annotate(
                        org_price=Case(
                            When(price__gt=0, then='price'),
                            default=None,
                            output_field=DecimalField(),
                        )
                    )
                    .values('org_price')[:1],  # subquery output
                ),
                'sale_price',
                output_field=DecimalField(),
            )
        )

        if request_category_id:
            products = products.filter(categories__id=request_category_id)

        if request_q:
            products = products.filter(
                Q(name_en__icontains=request_q) | Q(name_he__icontains=request_q)
            )

        # filter by categories
        if request_subcategories:
            products = products.filter(tags__in=request_subcategories.split(','))

        # filter by brands
        if request_brands:
            products = products.filter(brand__id__in=request_brands.split(','))

        # filter by min price
        if request_min_price:
            products = products.filter(
                Q(calculated_price__gte=request_min_price) | Q(calculated_price=0)
            )

        # filter by max price
        if request_max_price:
            if not request_including_tax:
                # add tax to the max price filter since we are always filtering
                # by the price which includes tax, but the user "works with"
                # prices which do not include tax if they chose the option
                request_max_price = request_max_price * (1 + settings.TAX_PERCENT / 100)

            products = products.filter(
                Q(calculated_price__lte=request_max_price) | Q(calculated_price=0)
            )

        # filter by product type
        if request_product_type:
            products = products.filter(product_kind__in=request_product_type.split(','))

        total_count = products.count()

        # a paginated query *must* have a definitive order_by
        order = 'calculated_price'
        if request_sort and request_sort == 'desc':
            order = '-calculated_price'
        products = products.order_by(order, 'id')

        paginator = Paginator(products, request_limit)
        page = paginator.get_page(request_page)

        products_serializer = QuickOfferProductsResponseSerializer(
            page,
            many=True,
            context={
                'quick_offer': quick_offer,
                'deduct_tax': not request_including_tax,
                **request_serializer.validated_data,
            },
        )

        return Response(
            {
                'success': True,
                'message': 'Quick offer products fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    'page_data': products_serializer.data,
                    'page_num': page.number,
                    'has_more': page.has_next(),
                    'total_count': total_count,
                },
            },
            status=status.HTTP_200_OK,
        )


class QuickOfferProductView(APIView):
    authentication_classes = [QuickOfferAuthentication]
    permission_classes = [QuickOfferPermissions]

    @method_decorator(lang_decorator)
    def get(self, request, product_id):
        quick_offer: QuickOffer = request.quick_offer

        request_serializer = QuickOfferProductRequestSerializer(data=request.GET)
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

        product = quick_offer.products.filter(id=product_id).first()
        if not product:
            return Response(
                {
                    'success': False,
                    'message': 'Product not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        request_including_tax = request_serializer.validated_data.get(
            'including_tax', True
        )

        serializer = QuickOfferProductSerializer(
            product,
            context={
                'quick_offer': quick_offer,
                'deduct_tax': not request_including_tax,
                **request_serializer.validated_data,
            },
        )
        return Response(
            {
                'success': True,
                'message': 'Product fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class QuickOfferSelectProductsView(APIView):
    authentication_classes = [QuickOfferAuthentication]
    permission_classes = [QuickOfferPermissions]

    def post(self, request):
        quick_offer: QuickOffer = request.quick_offer

        serializer = QuickOfferSelectProductsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        product_id = serializer.validated_data.get('product_id')
        quantity = serializer.validated_data.get('quantity')
        variations = serializer.validated_data.get('variations')
        lang = request.GET.get('lang', 'en')

        if variations and lang == 'he':
            variations = transform_variations(variations, mode='request')

        if not quick_offer.products.filter(id=product_id).exists():
            return Response(
                {
                    'success': False,
                    'message': 'Product not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        if not quantity:
            QuickOfferSelectedProduct.objects.filter(
                product=Product.objects.get(id=product_id),
                quick_offer=quick_offer,
            ).delete()
        else:
            QuickOfferSelectedProduct.objects.update_or_create(
                product=Product.objects.get(id=product_id),
                quick_offer=quick_offer,
                defaults={'quantity': quantity, 'variations': variations},
            )

        return Response(
            {
                'success': True,
                'message': 'Product selected successfully with quantity.',
                'status': status.HTTP_200_OK,
                'data': {},
            },
            status=status.HTTP_200_OK,
        )


class GetQuickOfferSelectProductsView(APIView):
    authentication_classes = [QuickOfferAuthentication]
    permission_classes = [QuickOfferPermissions]

    @method_decorator(lang_decorator)
    def get(self, request):
        request_serializer = QuickOfferProductRequestSerializer(data=request.GET)
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
        request_including_tax = request_serializer.validated_data.get(
            'including_tax', True
        )
        quick_offer: QuickOffer = request.quick_offer
        selected_quick_offer = (
            QuickOfferSelectedProduct.objects.filter(
                quick_offer=quick_offer, quantity__gt=0
            )
            .all()
            .order_by('id')
        )
        serializer = QuickOfferSelectProductsDetailSerializer(
            selected_quick_offer,
            many=True,
            context={
                'quick_offer': quick_offer,
                'deduct_tax': not request_including_tax,
                'lang': request.GET.get('lang', 'en'),
            },
        )
        return Response(
            {
                'success': True,
                'message': 'Selected Product fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    'products': serializer.data,
                },
            },
            status=status.HTTP_200_OK,
        )


class QuickOfferCategoriesView(APIView):
    authentication_classes = [QuickOfferAuthentication]
    permission_classes = [QuickOfferPermissions]

    @method_decorator(lang_decorator)
    def get(self, request):
        quick_offer: QuickOffer = request.quick_offer
        product_ids = quick_offer.products.all().values_list('id', flat=True)
        categories_id = CategoryProduct.objects.filter(
            product_id__in=product_ids
        ).values_list('category_id', flat=True)
        categories = Category.objects.filter(id__in=categories_id)
        serialized_categories = CategorySerializer(categories, many=True).data

        return Response(
            {
                'success': True,
                'message': 'Categories fetched successfully.',
                'code': 'categories_fetched',
                'status': status.HTTP_200_OK,
                'data': {'categories': serialized_categories},
            },
            status=status.HTTP_200_OK,
        )


class QuickOfferShareView(APIView):
    authentication_classes = [QuickOfferAuthentication]
    permission_classes = [QuickOfferPermissions]
    serializer = ShareRequestSerializer

    @method_decorator(lang_decorator)
    def post(self, request):
        serializer = ShareRequestSerializer(data=request.data)
        quick_offer = request.quick_offer
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product_ids = serializer.data.get('product_ids')
        share_type = serializer.data.get('share_type')

        if not isinstance(product_ids, list):
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': {'product_ids': ['A valid list of integers is required.']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_share_types = [choice.value for choice in ShareTypeEnum]
        if share_type not in valid_share_types:
            return Response(
                {
                    'success': False,
                    'message': 'Invalid share type provided.',
                    'code': 'invalid_share_type',
                    'status': status.HTTP_400_BAD_REQUEST,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if share_type == ShareTypeEnum.Cart.value:
            selected_products = QuickOfferSelectedProduct.objects.filter(
                quick_offer=quick_offer, quantity__gt=0
            )
        else:
            selected_products = QuickOfferSelectedProduct.objects.filter(
                quick_offer=quick_offer, product__id__in=product_ids
            )
        if not selected_products.exists():
            return Response(
                {
                    'success': False,
                    'message': 'No Products Selected.',
                    'code': 'no_products_selected',
                    'status': status.HTTP_400_BAD_REQUEST,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Create Share object
        share = Share.objects.create(
            share_type=share_type,
            quick_offer=quick_offer,
        )
        share.products.set(selected_products.values_list('product', flat=True))

        return Response(
            {
                'success': True,
                'message': 'Products shared successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    'share_id': share.share_id,
                },
            },
            status=status.HTTP_200_OK,
        )


class GetQuickOfferShareView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(lang_decorator)
    def get(self, request, share_id):
        request_serializer = QuickOfferProductRequestSerializer(data=request.GET)
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
        try:
            share = Share.objects.get(share_id=share_id)
        except Share.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'message': 'Share not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        response_data = {
            'share_type': share.share_type,
            'products': [],
            'cart': [],
        }
        request_including_tax = request_serializer.validated_data.get(
            'including_tax', True
        )

        if share.share_type == ShareTypeEnum.Product.value:
            product_shares = share.products.all()
            response_data['products'] = QuickOfferProductSerializer(
                product_shares,
                many=True,
                context={
                    'quick_offer': share.quick_offer,
                    'deduct_tax': request_including_tax,
                },
            ).data

        elif share.share_type == ShareTypeEnum.Cart.value:
            try:
                quick_offer = share.quick_offer
                products = quick_offer.selected_products.all()
                selected_products = QuickOfferSelectedProduct.objects.filter(
                    quick_offer=quick_offer, product__id__in=products, quantity__gt=0
                )

                response_data['cart'] = {
                    'products': QuickOfferSelectProductsDetailSerializer(
                        selected_products,
                        many=True,
                        context={
                            'quick_offer': quick_offer,
                            'deduct_tax': not request_including_tax,
                            'lang': request.GET.get('lang', 'en'),
                        },
                    ).data
                }

            except (Cart.DoesNotExist, AttributeError):
                return Response(
                    {
                        'success': False,
                        'message': 'Cart not found.',
                        'code': 'not_found',
                        'status': status.HTTP_404_NOT_FOUND,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(
            {
                'success': True,
                'message': 'Share details fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': response_data,
            },
            status=status.HTTP_200_OK,
        )


class QuickOfferImpersonationTokenExhcangeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, quick_offer_code):
        request_data = CampaignExchangeRequestSerializer(data=request.data)

        if not request_data.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_token = request_data.validated_data['t']

        impersonation_token = CampaignImpersonationToken.objects.filter(
            token=request_token,
            quick_offer__code=quick_offer_code,
            valid_until_epoch_seconds__gte=int(time()),
            used=False,
        ).first()

        if not impersonation_token:
            return Response(
                {
                    'success': False,
                    'message': 'Not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        token_payload = {
            'admin_id': impersonation_token.user.id,
            'quick_offer_id': impersonation_token.quick_offer.id,
        }

        auth_token = jwt_encode(token_payload)

        impersonation_token.used = True
        impersonation_token.save(update_fields=['used'])

        return Response(
            {
                'success': True,
                'message': 'Token exchanged successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    'auth_token': auth_token,
                },
            },
            status=status.HTTP_200_OK,
        )


class OrganizationView(APIView):
    authentication_classes = [SessionAuthentication]

    def get(self, request, organization_id):
        organization = Organization.objects.filter(id=organization_id).first()
        if not organization:
            return Response(
                {
                    'success': False,
                    'message': 'Organization not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        organization = OrganizationSerializer(
            organization,
            context={'field_names': [f.name for f in Organization._meta.fields]},
        ).data

        return Response(
            {
                'success': True,
                'message': 'Organization fetched successfully.',
                'status': status.HTTP_200_OK,
                'data': organization,
            },
            status=status.HTTP_200_OK,
        )


class OrganizationProductView(APIView):
    authentication_classes = [SessionAuthentication]

    def put(self, request):
        request_serializer = OrganizationProductPutSerializer(data=request.data)
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

        request_organization_id = request_serializer.validated_data.get('organization')
        request_product_id = request_serializer.validated_data.get('product')
        request_price = request_serializer.validated_data.get('price')

        organization_product = OrganizationProduct.objects.filter(
            organization=request_organization_id, product=request_product_id
        ).first()
        if organization_product:
            organization_product.price = request_price
        else:
            organization_product = OrganizationProduct.objects.create(
                organization=request_organization_id,
                product=request_product_id,
                price=request_price,
            )

        organization_product.save()
        response_serializer = OrganizationProductPutSerializer(organization_product)

        return Response(
            {
                'success': True,
                'message': 'Organization product updated successfully.',
                'status': status.HTTP_200_OK,
                'data': response_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class CampaignEmployeeSendInvitationView(APIView):
    authentication_classes = [SessionAuthentication]

    def post(self, request):
        request_serializer = CampaignEmployeeSendInvitationPostSerializer(
            data=request.data
        )
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

        request_data = request_serializer.validated_data
        campaign_employees = request_data.get('campaign_employees')
        send_invitation_type = request_data.get('send_invitation_type')
        campaign_id = request_data.get('campaign_id')

        if send_invitation_type and campaign_employees:
            send_invitation_employees = list(
                CampaignEmployee.objects.filter(id__in=campaign_employees).values_list(
                    'employee__id', flat=True
                )
            )
            if send_invitation_employees:
                send_campaign_employee_invitation.apply_async(
                    (campaign_id, send_invitation_employees, send_invitation_type)
                )

        return Response(
            {
                'success': True,
                'message': 'Invitation sending process has started',
                'status': status.HTTP_200_OK,
                'data': {},
            },
            status=status.HTTP_200_OK,
        )


class EmployeeGroupCampaignProductView(APIView):
    authentication_classes = [SessionAuthentication]

    def put(self, request):
        request_serializer = EmployeeGroupCampaignProductPutSerializer(
            data=request.data
        )
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

        request_data = request_serializer.validated_data
        product_id = request_data.get('product_id')
        company_cost_per_employee = request_data.get('company_cost_per_employee')

        employee_group_campaign_product = EmployeeGroupCampaignProduct.objects.filter(
            product_id=product_id
        ).first()
        if not employee_group_campaign_product:
            return Response(
                {
                    'success': False,
                    'message': 'Employee group campaign product not found.',
                    'code': 'not_found',
                    'status': status.HTTP_404_NOT_FOUND,
                    'data': {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if company_cost_per_employee:
            employee_group_campaign_product.company_cost_per_employee = (
                company_cost_per_employee
            )

        employee_group_campaign_product.save()

        return Response(
            {
                'success': True,
                'message': 'Employee group campaign product updated successfully.',
                'status': status.HTTP_200_OK,
                'data': {},
            },
            status=status.HTTP_200_OK,
        )
