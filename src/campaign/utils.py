from django.conf import settings
from django.contrib.auth import get_user_model
import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission

from campaign.models import (
    Campaign,
    CampaignEmployee,
    Employee,
    EmployeeGroupCampaign,
    OrganizationProduct,
    QuickOffer,
)
from inventory.models import Product


UserModel = get_user_model()


class EmployeeAuthentication(BaseAuthentication):
    def authenticate(self, request):
        try:
            auth = request.headers.get('X-Authorization')
            if isinstance(auth, str) and auth.startswith('Bearer '):
                token = auth.replace('Bearer ', '')
                if len(token) > 0:
                    decoded_token = jwt.decode(
                        jwt=token,
                        key=settings.JWT_SECRET_KEY,
                        algorithms=[settings.JWT_ALGORITHM],
                    )
                    if isinstance(decoded_token, dict):
                        if decoded_token.get('employee_id'):
                            employee = Employee.objects.get(
                                pk=decoded_token.get('employee_id')
                            )
                            return (employee, token)
                        elif decoded_token.get(
                            'impersonated_employee_id'
                        ) and decoded_token.get('admin_id'):
                            campaign_employee = CampaignEmployee.objects.get(
                                pk=decoded_token.get('impersonated_employee_id')
                            )
                            employee = campaign_employee.employee
                            impersonator_admin = UserModel.objects.get(
                                pk=decoded_token.get('admin_id')
                            )

                            _set_employee_impersonated_by(employee, impersonator_admin)

                            return (employee, token)
        except Exception:
            pass

        return None

    def authenticate_header(self, request):
        return 'Bearer'


class EmployeePermissions(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, Employee)


class AdminPreviewAuthentication(BaseAuthentication):
    def authenticate(self, request):
        try:
            auth = request.headers.get('X-Authorization')
            if isinstance(auth, str) and auth.startswith('Bearer '):
                token = auth.replace('Bearer ', '')
                if len(token) > 0:
                    decoded_token = jwt.decode(
                        jwt=token,
                        key=settings.JWT_SECRET_KEY,
                        algorithms=[settings.JWT_ALGORITHM],
                    )
                    if isinstance(decoded_token, dict):
                        if decoded_token.get('admin_preview') and decoded_token.get(
                            'admin_id'
                        ):
                            employee_group_campaign = EmployeeGroupCampaign.objects.get(
                                id=decoded_token.get('employee_group_campaign_id')
                            )

                            preview_employee = Employee(
                                employee_group=employee_group_campaign.employee_group,
                                first_name='Admin',
                                last_name='Admin',
                            )
                            _set_employee_admin_preview(preview_employee)

                            return (
                                preview_employee,
                                token,
                            )
        except Exception:
            pass

        return None

    def authenticate_header(self, request):
        return 'Bearer'


def get_campaign_product_price(campaign: Campaign, product: Product) -> int:
    organization_product = OrganizationProduct.objects.filter(
        organization=campaign.organization, product=product
    ).first()

    if organization_product and organization_product.price:
        return organization_product.price
    else:
        return product.sale_price


def get_quick_offer_product_price(quick_offer: QuickOffer, product: Product) -> int:
    organization_product = OrganizationProduct.objects.filter(
        organization=quick_offer.organization, product=product
    ).first()

    if organization_product and organization_product.price:
        return organization_product.price
    else:
        return product.sale_price


def _set_employee_admin_preview(employee: Employee) -> None:
    employee._admin_preview = True


def get_employee_admin_preview(employee: Employee) -> bool:
    return getattr(employee, '_admin_preview', False)


def _set_employee_impersonated_by(employee: Employee, admin_user: UserModel) -> None:
    employee._impersonated_by = admin_user.pk


def get_employee_impersonated_by(employee: Employee) -> bool:
    return getattr(employee, '_impersonated_by', None)


def format_with_none_replacement(format_string, **kwargs):
    cleaned_kwargs = {
        key: (
            f' ({value})'
            if key == 'delivery_additional_details' and value is not None
            else (
                f'{value}, '
                if (
                    (
                        key == 'delivery_street_number'
                        or key == 'delivery_apartment_number'
                    )
                    and value is not None
                )
                else (value if value is not None else '')
            )
        )
        for key, value in kwargs.items()
    }
    return format_string.format(**cleaned_kwargs)


class QuickOfferAuthentication(BaseAuthentication):
    def authenticate(self, request):
        try:
            auth = str(request.headers.get('X-Authorization'))
            assert auth.startswith('Bearer ')
            token = auth.replace('Bearer ', '')
            assert len(token)
            decoded_token = jwt.decode(
                jwt=token,
                key=settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            assert isinstance(decoded_token, dict)
            quick_offer_id = int(decoded_token.get('quick_offer_id'))
            quick_offer = QuickOffer.objects.get(id=quick_offer_id)
            setattr(request, 'quick_offer', quick_offer)
            return (None, token)
        except Exception:
            pass

        return None

    def authenticate_header(self, request):
        return 'Bearer'


class QuickOfferPermissions(BasePermission):
    def has_permission(self, request, view):
        return (
            isinstance(getattr(request, 'quick_offer', None), QuickOffer)
            and request.quick_offer.status == QuickOffer.StatusEnum.ACTIVE.name
        )
