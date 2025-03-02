from enum import Enum

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from campaign.models import Order, OrderProduct

from .enums import LogisticsCenterEnum, LogisticsCenterMessageTypeEnum


class PurchaseOrder(models.Model):
    class Status(Enum):
        PENDING = 'Pending'
        SENT_TO_SUPPLIER = 'Sent to supplier'
        APPROVED = 'Approved'
        CANCELLED = 'Cancelled'

    supplier = models.ForeignKey('inventory.Supplier', on_delete=models.CASCADE)
    notes = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=100,
        choices=[(s.name, s.value) for s in Status],
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    logistics_center = models.CharField(
        max_length=100,
        choices=[(c.name, c.value) for c in LogisticsCenterEnum],
        null=True,
        blank=True,
    )
    sent_to_logistics_center_at = models.DateTimeField(null=True)
    logistics_center_id = models.CharField(max_length=64, null=True, blank=True)
    logistics_center_status = models.CharField(max_length=32, null=True, blank=True)

    @property
    def po_number(self):
        return self.pk

    @property
    def products(self):
        return PurchaseOrderProduct.objects.filter(purchase_order=self)

    @property
    def total_cost(self):
        return sum([p.total_cost for p in self.products.all()])

    def approve(self):
        from .tasks import send_purchase_order_to_logistics_center

        if self.status != PurchaseOrder.Status.APPROVED.name:
            errors = []
            for p in self.products:
                if p.product_id.sku and len(p.product_id.sku) > 22:
                    errors.append(
                        f'Product {p.product_id.name} has a sku value which '
                        'is too long'
                    )
                if p.product_id.reference and len(p.product_id.reference) > 22:
                    errors.append(
                        f'Product {p.product_id.name} has a reference value '
                        'which is too long'
                    )

            if errors:
                raise ValidationError(', '.join(errors))

            self.status = PurchaseOrder.Status.APPROVED.name

            # use this flag to let the pre-save signak know this change is made
            # from the right place
            self._approved_by_func = True
            self.save(update_fields=['status'])
            delattr(self, '_approved_by_func')

            # we only have one active logistics provider (=center) at the moment,
            # but in the future some stock and orders may be managed by one while
            # others by another according to some logic
            send_purchase_order_to_logistics_center.apply_async(
                (self.id, settings.ACTIVE_LOGISTICS_CENTER)
            )
        else:
            raise ValidationError(
                f'Purchase order {self.po_number} is already approved'
            )


class PurchaseOrderProduct(models.Model):
    product_id = models.ForeignKey('inventory.Product', on_delete=models.CASCADE)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE)
    quantity_ordered = models.PositiveIntegerField()
    quantity_sent_to_logistics_center = models.PositiveIntegerField()
    variations = models.JSONField(null=True, blank=True)

    @property
    def total_cost(self):
        return self.product_id.cost_price * self.quantity_ordered

    @property
    def quantity_arrived(self):
        """
        this is implemented as a property running queries for ease and because
        currently purchase orders don't contain many products each. if this
        becomes another performance violator this should be added as an
        annotation to the model manager's queryset
        """

        quantity = LogisticsCenterInboundReceiptLine.objects.filter(
            purchase_order_product_id=self.id
        ).aggregate(models.Sum('quantity_received'))
        return quantity.get('quantity_received__sum') or 0


class PurchaseOrderSentLog(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE)
    sent_datetime = models.DateTimeField()


class POOrder(PurchaseOrder):
    class Meta:
        proxy = True
        verbose_name = 'PO Order'
        verbose_name_plural = 'PO Orders'


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


class LogisticsCenterInboundStatus(models.Model):
    logistics_center_message = models.ForeignKey(
        LogisticsCenterMessage, on_delete=models.SET_NULL, null=True
    )
    center = models.CharField(
        max_length=100,
        choices=[(c.name, c.value) for c in LogisticsCenterEnum],
    )
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE)
    status = models.CharField(max_length=32)
    status_date_time = models.DateTimeField()


class LogisticsCenterInboundReceipt(models.Model):
    center = models.CharField(
        max_length=100,
        choices=[(c.name, c.value) for c in LogisticsCenterEnum],
    )
    receipt_code = models.CharField(max_length=64)
    receipt_start_date = models.DateTimeField()
    receipt_close_date = models.DateTimeField(null=True)
    status = models.CharField(max_length=32, null=True)


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
    status = models.CharField(max_length=32)
    status_date_time = models.DateTimeField()


class EmployeeOrderProduct(OrderProduct):
    class Meta:
        proxy = True
        verbose_name = 'Order Summary'
        verbose_name_plural = 'Order Summaries'


class LogisticsCenterStockSnapshot(models.Model):
    center = models.CharField(
        max_length=100,
        choices=[(c.name, c.value) for c in LogisticsCenterEnum],
    )
    snapshot_date_time = models.DateTimeField()
    snapshot_file_path = models.TextField()
    processed_date_time = models.DateTimeField()


class LogisticsCenterStockSnapshotLine(models.Model):
    stock_snapshot = models.ForeignKey(
        LogisticsCenterStockSnapshot, on_delete=models.CASCADE, related_name='lines'
    )
    sku = models.TextField()
    quantity = models.PositiveIntegerField()
