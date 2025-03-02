from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save

from .models import POOrder, PurchaseOrder


def purchase_order_pre_save(instance, **kwargs):
    try:
        old_instance = PurchaseOrder.objects.get(pk=instance.pk)

        # make sure that we only change the purchase order's status to approved
        # from the `approve` function and not by directly changing the status
        if (
            instance.status != old_instance.status
            and instance.status == PurchaseOrder.Status.APPROVED.name
            and not getattr(instance, '_approved_by_func', False)
        ):
            raise ValidationError(
                'To approve a purchase order you *must* call its `approve` function'
            )
    except PurchaseOrder.DoesNotExist:
        pass


# connect the purchase order model and its proxy manually to the signals
pre_save.connect(purchase_order_pre_save, sender=PurchaseOrder)
pre_save.connect(purchase_order_pre_save, sender=POOrder)
