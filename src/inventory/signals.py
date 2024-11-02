from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Product


@receiver(pre_save, sender=Product)
def on_change(sender, instance: Product, **kwargs):
    if instance.id is None:
        pass
    else:
        try:
            previous = Product.objects.get(id=instance.id)
            if previous.product_quantity != instance.product_quantity:
                instance.alert_stock_sent = False
        except Product.DoesNotExist:
            pass
