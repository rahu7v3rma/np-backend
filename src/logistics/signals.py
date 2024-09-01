from django.db.models.signals import post_save, pre_save

from .models import POOrder, PurchaseOrder
from .tasks import send_purchase_order_to_logistics_center


def purchase_order_pre_save(instance, **kwargs):
    try:
        # keep the previous status so we know in post_save if the purchase
        # order was just approved
        old_instance = PurchaseOrder.objects.get(pk=instance.pk)
        instance._previous_status = old_instance.status
    except PurchaseOrder.DoesNotExist:
        instance._previous_status = False


def purchase_order_post_save(instance, **kwargs):
    # if the status changed and is now approved we should communicate with the
    # logistics center
    if (
        instance.status != instance._previous_status
        and instance.status == PurchaseOrder.Status.APPROVED.name
    ):
        send_purchase_order_to_logistics_center.apply_async((instance.id,))


# connect the purchase order model and its proxy manually to the signals
pre_save.connect(purchase_order_pre_save, sender=PurchaseOrder)
pre_save.connect(purchase_order_pre_save, sender=POOrder)
post_save.connect(purchase_order_post_save, sender=PurchaseOrder)
post_save.connect(purchase_order_post_save, sender=POOrder)
