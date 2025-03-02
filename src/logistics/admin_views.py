from django.core.exceptions import ValidationError
from django.db.models import F, Sum
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from campaign.tasks import send_purchase_order_email
from logistics.utils import update_order_products_po_status

from .models import EmployeeOrderProduct, PurchaseOrder, PurchaseOrderProduct
from .serializers import PurchaseOrderProductSerializer, PurchaseOrderSerializer


class AddProductsOrderView(APIView):
    authentication_classes = [SessionAuthentication]

    def post(self, request):
        serializer = PurchaseOrderSerializer(data=request.data)
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

        order: PurchaseOrder = serializer.save()

        products_data = request.data.get('products')

        for product_data in products_data:
            emp_pr_order = EmployeeOrderProduct.objects.filter(
                pk=product_data.get('order')
            ).first()
            if emp_pr_order:
                product_data['variations'] = emp_pr_order.variations
            product_data['purchase_order'] = order.id

        products_serializer = PurchaseOrderProductSerializer(
            data=products_data, many=True
        )

        if not products_serializer.is_valid():
            order.delete()
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': products_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        products_serializer.save()

        if order.status == PurchaseOrder.Status.SENT_TO_SUPPLIER.name:
            send_purchase_order_email.apply_async((order.pk, 'he'))

        return Response(
            {
                'success': True,
                'message': 'Purchase order created successfully.',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        instance: PurchaseOrder = PurchaseOrder.objects.get(pk=pk)
        serializer = PurchaseOrderSerializer(instance, data=request.data)
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

        order: PurchaseOrder = serializer.save()
        products_data = request.data.get('products')

        for product_data in products_data:
            emp_pr_order = EmployeeOrderProduct.objects.filter(
                pk=product_data.get('order')
            ).first()
            if emp_pr_order:
                product_data['variations'] = emp_pr_order.variations
            product_data['purchase_order'] = order.id

        products_serializer = PurchaseOrderProductSerializer(
            data=products_data, many=True
        )

        if not products_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': products_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.products.delete()
        products_serializer.save()
        total_quantity_arrived = 0
        if order.status == PurchaseOrder.Status.APPROVED.name:
            total_quantity_arrived = (
                PurchaseOrderProduct.objects.filter(purchase_order=order).aggregate(
                    total_arrived=Sum(F('quantity_sent_to_logistics_center'))
                )['total_arrived']
                or 0
            )

        if order.status == PurchaseOrder.Status.SENT_TO_SUPPLIER.name:
            send_purchase_order_email.apply_async((order.pk, 'he'))

        update_order_products_po_status(purchase_order=order)

        return Response(
            {
                'success': True,
                'message': 'Purchase order Updated successfully.',
                'status': status.HTTP_200_OK,
                'data': {
                    **serializer.data,
                    'arrival': total_quantity_arrived,
                },
            },
            status=status.HTTP_200_OK,
        )


class UpdateStatusProductsOrderView(APIView):
    authentication_classes = [SessionAuthentication]

    def patch(self, request, pk):
        instance = PurchaseOrder.objects.get(pk=pk)

        try:
            instance.approve()

            return Response(
                {
                    'success': True,
                    'message': 'Purchase order Updated successfully.',
                    'status': status.HTTP_200_OK,
                },
                status=status.HTTP_200_OK,
            )
        except ValidationError as ex:
            return Response(
                {
                    'success': False,
                    'message': ex.message,
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
