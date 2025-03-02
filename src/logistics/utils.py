from django.conf import settings
from django.db.models import Q

from campaign.models import OrderProduct
from inventory.models import Variation
from logistics.models import PurchaseOrder, PurchaseOrderProduct


def get_variation_type(variation):
    var_obj = Variation.objects.filter(
        Q(system_name_en=variation)
        | Q(system_name_he=variation)
        | Q(site_name_en=variation)
        | Q(site_name_he=variation)
    ).first()
    return var_obj.variation_kind


def get_variations_string(variations: dict) -> str:
    variations = variations if isinstance(variations, dict) else {}
    variations_text = []
    for key, value in variations.items():
        variation_kind = get_variation_type(variation=key)
        if variation_kind == 'COLOR':
            variations_text.insert(0, str(value[:2]))
        elif variation_kind == 'TEXT':
            variations_text.append(str(value[:1]))
    return ''.join(variations_text)


def exclude_taxes(value):
    """
    return price without taxes
    """
    return round(value * (1 - settings.TAX_PERCENT / 100), 2)


def update_order_products_po_status(purchase_order: PurchaseOrder):
    order_products = OrderProduct.objects.filter(
        product_id__product_id__id__in=list(
            PurchaseOrderProduct.objects.filter(
                purchase_order=purchase_order
            ).values_list('product_id__id', flat=True)
        )
    )
    if purchase_order.status == PurchaseOrder.Status.PENDING.name:
        order_products.update(po_status=OrderProduct.POStatus.WAITING.name)
    if purchase_order.status == PurchaseOrder.Status.SENT_TO_SUPPLIER.name:
        order_products.update(po_status=OrderProduct.POStatus.PO_SENT.name)
    if purchase_order.status == PurchaseOrder.Status.APPROVED.name:
        order_products.update(po_status=OrderProduct.POStatus.IN_TRANSIT.name)
