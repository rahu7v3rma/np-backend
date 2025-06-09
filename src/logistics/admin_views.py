from urllib.parse import parse_qsl

from django.core.exceptions import ValidationError
from django.db.models import (
    F,
    Q,
    Sum,
)
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from campaign.models import (
    Order,
    OrderProduct,
)
from inventory.models import Product

from .models import EmployeeOrderProduct, PurchaseOrder, PurchaseOrderProduct
from .serializers import PurchaseOrderProductSerializer, PurchaseOrderSerializer
from .tasks import send_purchase_order_to_supplier


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

        original_products_data = request.data.get('products')
        products_data = []

        # handle bundles case
        for product in original_products_data:
            product_instance = Product.objects.get(id=product.get('product_id'))
            if product_instance.product_kind != Product.ProductKindEnum.BUNDLE.name:
                products_data.append(product)
                continue
            products_data = [
                *products_data,
                *[
                    {
                        **product,
                        **{
                            'bundle': product_instance.id,
                            'product_id': bundled.product.id,
                            'quantity_ordered': bundled.quantity
                            * max(product.get('quantity_ordered'), 1),
                            'bundle_quantity': product.get('quantity_ordered'),
                        },
                    }
                    for bundled in product_instance.bundled_items.all()
                ],
            ]

        # these are filters made to the order summaries page if the po creation
        # process started there. if the parameter was not passed the dict will
        # be empty
        order_product_changelist_filters = dict(
            parse_qsl(request.data.get('changelist_filters'))
        )

        # split and unmask multi-value filter values
        for key, value in order_product_changelist_filters.items():
            if key.endswith('__in'):
                order_product_changelist_filters[key] = [
                    v.replace('%~', ',') for v in value.split(',')
                ]

        for product_data in products_data:
            required_quantity = product_data.get(
                'bundle_quantity', product_data.get('quantity_ordered')
            )

            order_products = self.get_matching_quantity_products(
                product_data.get('bundle', product_data.get('product_id')),
                required_quantity,
                product_data.get('voucher_value'),
                order_product_changelist_filters,
            )
            if not len(order_products):
                # Delete the new PO if the validation fails.
                order.delete()

                message = (
                    'Not enough available campaign orders for product '
                    f'{product_data.get("product_id")}'
                )
                if product_data.get('voucher_value'):
                    message += f' (value {product_data.get("voucher_value")})'

                return Response(
                    {
                        'success': False,
                        'message': message,
                        'code': 'request_invalid',
                        'status': status.HTTP_400_BAD_REQUEST,
                        'data': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            product_data['variations'] = product_data.get('variations')
            product_data['purchase_order'] = order.id

        final_products_data = []

        for pd in products_data:
            orders = pd.pop('orders')
            if not orders:
                final_products_data.append(pd.copy())
                continue
            for _order in orders:
                final_products_data.append(
                    {**pd, **{'order_product': OrderProduct.objects.get(id=_order).pk}}
                )

        products_serializer = PurchaseOrderProductSerializer(
            data=final_products_data, many=True
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

        po_products = products_serializer.save()
        for po_product in po_products:
            isMoneyProduct = po_product.product_id.product_kind = 'MONEY'
            order_products = self.get_matching_quantity_products(
                po_product.product_id.id,
                po_product.quantity_ordered,
                po_product.voucher_value if isMoneyProduct else 0,
                order_product_changelist_filters,
            )

            for order_product in order_products:
                order_product.purchase_order_product = po_product
                order_product.save()

        if order.status == PurchaseOrder.Status.SENT_TO_SUPPLIER.name:
            send_purchase_order_to_supplier.apply_async((order.pk, 'he'))

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
        po_id = request.resolver_match.kwargs.get('pk', None)
        for product_data in products_data:
            if product_data.get('voucher_value'):
                # Since we round the voucher to one decimal place during creation
                # We have to do same here
                voucher_value = round(float(product_data.get('voucher_value')), 1)
            else:
                voucher_value = None
            required_quantity = product_data.get('quantity_ordered')
            product_id = product_data.get('product_id')
            po_product = PurchaseOrderProduct.objects.filter(
                Q(product_id__id=product_id)
                | Q(order_product__product_id__product_id__id=product_id),
                purchase_order_id=po_id,
                voucher_value=voucher_value,
            ).first()
            if not po_product:
                return Response(
                    {
                        'success': False,
                        'message': (
                            'No purchase order product found '
                            'with the provided purchase order id '
                        ),
                        'code': 'request_invalid',
                        'status': status.HTTP_400_BAD_REQUEST,
                        'data': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            _, _, _, is_valid = self.get_matching_quantity_product_for_update(
                po_product.id, required_quantity, product_id, po_product.voucher_value
            )
            if not is_valid:
                message = (
                    f'Not enough available campaign orders for product {product_id}'
                )
                if po_product.voucher_value:
                    message += f' (value {po_product.voucher_value})'

                return Response(
                    {
                        'success': False,
                        'message': message,
                        'code': 'request_invalid',
                        'status': status.HTTP_400_BAD_REQUEST,
                        'data': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            emp_pr_order = (
                EmployeeOrderProduct.objects.filter(
                    product_id__product_id=product_id,
                    order_id__status__in=[
                        Order.OrderStatusEnum.PENDING.name,
                        Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
                    ],
                )
                .annotate()
                .first()
            )

            product_data['variations'] = emp_pr_order.variations
            product_data['purchase_order'] = order.id

        original_products_data = products_data.copy()  # handle bundles case
        products_data = []
        for product in original_products_data:
            product_instance = Product.objects.get(id=product.get('product_id'))
            if product_instance.product_kind != Product.ProductKindEnum.BUNDLE.name:
                products_data.append(product)
                continue
            products_data = [
                *products_data,
                *[
                    {
                        **product,
                        **{
                            'bundle': product_instance.id,
                            'product_id': bundled.product.id,
                            'quantity_ordered': bundled.quantity
                            * max(product.get('quantity_ordered'), 1),
                            'bundle_quantity': product.get('quantity_ordered'),
                        },
                    }
                    for bundled in product_instance.bundled_items.all()
                ],
            ]
        # Fetch the instances and pass them
        for product_data in products_data:
            if product_data.get('voucher_value'):
                # Since we round the voucher to one decimal place during creation
                # We have to do same here
                voucher_value = round(float(product_data.get('voucher_value')), 1)
            else:
                voucher_value = None
            product_id = product_data.get('product_id')
            product_data['voucher_value'] = voucher_value
            purchase_order_product = PurchaseOrderProduct.objects.filter(
                purchase_order_id=instance.id,
                product_id_id=product_id,
                voucher_value=voucher_value,
            ).first()
            product_serializer = PurchaseOrderProductSerializer(
                purchase_order_product, data=product_data, partial=True
            )
            if not product_serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Request is invalid.',
                        'code': 'request_invalid',
                        'status': status.HTTP_400_BAD_REQUEST,
                        'data': product_serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # order.products.delete()
            po_product = product_serializer.save()
            required_quantity = po_product.quantity_ordered
            (
                _,
                updated_order_products,
                prev_total_quantity,
                is_valid,
            ) = self.get_matching_quantity_product_for_update(
                po_product.id,
                product_data.get('bundle_quantity', required_quantity),
                product_data.get('bundle', product_id),
                po_product.voucher_value,
            )
            if not is_valid:
                message = (
                    f'Not enough available campaign orders for product {product_id}'
                )
                if po_product.voucher_value:
                    message += f' (value {po_product.voucher_value})'

                return Response(
                    {
                        'success': False,
                        'message': message,
                        'code': 'request_invalid',
                        'status': status.HTTP_400_BAD_REQUEST,
                        'data': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if required_quantity > prev_total_quantity:
                # The order quantity has been increased
                for order_product in updated_order_products:
                    order_product.purchase_order_product = po_product
                    order_product.save()
            elif required_quantity < prev_total_quantity:
                # The order quantity has been decreased
                for order_product in updated_order_products:
                    order_product.purchase_order_product = None
                    order_product.save()

        total_quantity_arrived = 0
        if order.status == PurchaseOrder.Status.APPROVED.name:
            total_quantity_arrived = (
                PurchaseOrderProduct.objects.filter(purchase_order=order).aggregate(
                    total_arrived=Sum(F('quantity_sent_to_logistics_center'))
                )['total_arrived']
                or 0
            )

        if order.status == PurchaseOrder.Status.SENT_TO_SUPPLIER.name:
            send_purchase_order_to_supplier.apply_async((order.pk, 'he'))

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

    def get_matching_quantity_products(
        self,
        product_id,
        required_quantity,
        voucher_value,
        order_product_changelist_filters,
    ):
        """
        Helper method to get the order products that match quantity of a purchase order
        required quantity that has not been linked to any PurchaseOrderProduct.

        Args:
            product_id (str): The product ID to filter the EmployeeOrderProduct.
            required_quantity(int): the required quantity of purchase order product
            voucher_value(int | None): optional voucher value of purchase order product
            order_product_changelist_filters(dict): dictionary containing filters to be
                                                    applied to order products query

        Returns:
            list: order products that match the required quantity
        """
        sum_quantity = 0
        if 'e' in order_product_changelist_filters.keys():
            order_product_changelist_filters.pop('e')
        if (
            'product_id__product_id__supplier__name__in'
            in order_product_changelist_filters.keys()
        ):
            order_product_changelist_filters.pop(
                'product_id__product_id__supplier__name__in'
            )
        if 'exclude_columns' in order_product_changelist_filters.keys():
            order_product_changelist_filters.pop('exclude_columns')

        if 'include_columns' in order_product_changelist_filters.keys():
            order_product_changelist_filters.pop('include_columns')

        if 'columns_order' in order_product_changelist_filters.keys():
            order_product_changelist_filters.pop('columns_order')

        products = OrderProduct.objects.filter(
            **order_product_changelist_filters,
            product_id__product_id=product_id,
            purchase_order_product__isnull=True,
            order_id__status__in=[
                Order.OrderStatusEnum.PENDING.name,
                Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
            ],
            voucher_val=voucher_value,
        )

        order_products = []
        for product in products:
            sum_quantity += product.quantity
            if sum_quantity == required_quantity:
                order_products.append(product)
                break
            elif sum_quantity < required_quantity:
                order_products.append(product)
            elif sum_quantity > required_quantity:
                order_products = []
                break

        # if after iterating all products we don't have enough quantity
        # it should return empty because it doesn't meet the exact required quantity
        if sum_quantity < required_quantity:
            order_products = []

        return order_products

    def get_matching_quantity_product_for_update(
        self, po_product_id, required_quantity, product_id, voucher_value
    ):
        """
        Helper method to get the purchase order products that match the required
        quantity and po_id.

        Args:
            po_id (str): The purchase order product ID to filter the `OrderProduct`.
            required_quantity (int): The required quantity of purchase order products.
            voucher_value: optional voucher value of purchase order product
        Returns:
            tuple: the previous order products that match the required quantity and the
            unattached order product , prev_quantity to check weather action, and  a
            boolean that checks the validity products
        """
        previous_order_product = OrderProduct.objects.filter(
            Q(purchase_order_product=po_product_id)
            | Q(purchaseorderproduct__id=po_product_id),
            product_id__product_id=product_id,
            order_id__status__in=[
                Order.OrderStatusEnum.PENDING.name,
                Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
            ],
        )
        if not previous_order_product:
            return [], [], 0, False
        order_products = []
        prev_total_quantity = previous_order_product.aggregate(
            total_quantity=Sum('quantity')
        )['total_quantity']
        total_quantity = prev_total_quantity
        if total_quantity == required_quantity:
            # no change has been applied
            return previous_order_product, [], prev_total_quantity, True
        elif total_quantity < required_quantity:
            # since the total quantity is less find the unattached and attache it
            products = OrderProduct.objects.filter(
                product_id__product_id=product_id,
                purchase_order_product__isnull=True,
                order_id__status__in=[
                    Order.OrderStatusEnum.PENDING.name,
                    Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
                ],
                voucher_val=voucher_value,
            )
            for product in products:
                total_quantity += product.quantity
                if total_quantity == required_quantity:
                    order_products.append(product)
                    break
                elif total_quantity < required_quantity:
                    order_products.append(product)
                elif total_quantity > required_quantity:
                    order_products = []
                    break

            # if after iterating all products we don't have enough quantity
            # it should return empty because it doesn't meet the exact required quantity
            if total_quantity != required_quantity:
                order_products = []
        else:
            for product in previous_order_product:
                total_quantity -= product.quantity
                if total_quantity == required_quantity:
                    order_products.append(product)
                    break
                elif total_quantity > required_quantity:
                    order_products.append(product)
                elif total_quantity <= 0:
                    # if we don't get the required quantity and reach 0 or less break
                    break

            # if after iterating all products we don't have enough quantity
            # it should return empty because it doesn't meet the exact required quantity
            if total_quantity != required_quantity:
                order_products = []

        return (
            previous_order_product,
            order_products,
            prev_total_quantity,
            total_quantity == required_quantity,
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
