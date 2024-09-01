from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from campaign.tasks import send_purchase_order_email

from .models import PurchaseOrder
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
            send_purchase_order_email.apply_async((order.pk,))

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

        if order.status == PurchaseOrder.Status.SENT_TO_SUPPLIER.name:
            send_purchase_order_email.apply_async((order.pk,))

        return Response(
            {
                'success': True,
                'message': 'Purchase order Updated successfully.',
                'status': status.HTTP_200_OK,
                'data': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class UpdateStatusProductsOrderView(APIView):
    authentication_classes = [SessionAuthentication]

    def patch(self, request, pk):
        instance = PurchaseOrder.objects.get(pk=pk)
        instance.status = PurchaseOrder.Status.APPROVED.name
        instance.save()
        return Response(
            {
                'success': True,
                'message': 'Purchase order Updated successfully.',
                'status': status.HTTP_200_OK,
            },
            status=status.HTTP_200_OK,
        )
