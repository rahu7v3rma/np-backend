from enum import Enum

from django.db import models

from campaign.models import Order, OrderProduct
from inventory.models import Product, Supplier


class PurchaseOrder(models.Model):
    class Status(Enum):
        PENDING = 'Pending'
        SENT_TO_SUPPLIER = 'Sent to supplier'
        APPROVED = 'Approved'
        CANCELLED = 'Cancelled'

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    notes = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=100,
        choices=[(s.name, s.value) for s in Status],
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_to_logistics_center_at = models.DateTimeField(null=True)

    @property
    def po_number(self):
        return self.pk

    @property
    def products(self):
        return PurchaseOrderProduct.objects.filter(purchase_order=self)

    @property
    def total_cost(self):
        return sum([p.total_cost for p in self.products.all()])


class PurchaseOrderProduct(models.Model):
    product_id = models.ForeignKey(Product, on_delete=models.CASCADE)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE)
    quantity_ordered = models.PositiveIntegerField()
    quantity_sent_to_logistics_center = models.PositiveIntegerField()

    @property
    def total_cost(self):
        return self.product_id.cost_price * self.quantity_ordered


class PurchaseOrderSentLog(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE)
    sent_datetime = models.DateTimeField()


class POOrder(PurchaseOrder):
    class Meta:
        proxy = True
        verbose_name = 'PO Order'
        verbose_name_plural = 'PO Orders'


class LogisticsCenterEnum(Enum):
    ORIAN = 'Orian'


class LogisticsCenterMessageTypeEnum(Enum):
    INBOUND_RECEIPT = 'Inbound receipt'
    ORDER_STATUS_CHANGE = 'Order status change'
    SHIP_ORDER = 'Ship order'


class LogisticsCenterMessage(models.Model):
    center = models.CharField(
        max_length=100,
        choices=[(c.name, c.value) for c in LogisticsCenterEnum],
    )
    message_type = models.CharField(
        max_length=100,
        choices=[(mt.name, mt.value) for mt in LogisticsCenterMessageTypeEnum],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    raw_body = models.TextField()


class LogisticsCenterInboundReceipt(models.Model):
    center = models.CharField(
        max_length=100,
        choices=[(c.name, c.value) for c in LogisticsCenterEnum],
    )
    receipt_code = models.CharField(max_length=16)
    receipt_start_date = models.DateTimeField()
    receipt_close_date = models.DateTimeField()


class LogisticsCenterInboundReceiptLine(models.Model):
    logistics_center_message = models.ForeignKey(
        LogisticsCenterMessage, on_delete=models.SET_NULL, null=True
    )
    receipt = models.ForeignKey(LogisticsCenterInboundReceipt, on_delete=models.CASCADE)
    receipt_line = models.PositiveIntegerField()
    purchase_order_product = models.ForeignKey(
        PurchaseOrderProduct, on_delete=models.CASCADE
    )
    quantity_received = models.PositiveIntegerField()


class LogisticsCenterOrderStatus(models.Model):
    logistics_center_message = models.ForeignKey(
        LogisticsCenterMessage, on_delete=models.SET_NULL, null=True
    )
    center = models.CharField(
        max_length=100,
        choices=[(c.name, c.value) for c in LogisticsCenterEnum],
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    status = models.CharField(max_length=16)
    status_date_time = models.DateTimeField()


class EmployeeOrderProduct(OrderProduct):
    class Meta:
        proxy = True
        verbose_name = 'Order Summary'
        verbose_name_plural = 'Order Summaries'
