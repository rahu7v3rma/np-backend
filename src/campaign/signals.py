import secrets

from django.db import transaction  # Import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import (
    Campaign,
    CampaignEmployee,
    Employee,
    Order,
    QuickOffer,
)


@receiver(pre_save, sender=Campaign)
def create_campaign_code(sender, instance, **kwargs):
    # generate the campaign code only if a code has not been generated yet
    if not instance.code:
        instance.code = secrets.token_hex(8)


@receiver(pre_save, sender=QuickOffer)
def create_quick_offer_code(sender, instance, **kwargs):
    # generate the quick offer code only if a code has not been generated yet
    if not instance.code:
        instance.status = QuickOffer.StatusEnum.ACTIVE.name
        instance.code = secrets.token_hex(8)


@receiver(post_save, sender=Employee)
def connect_employee_to_active_campaigns(sender, instance, **kwargs):
    active_campaigns = instance.employee_group.campaigns.filter(
        status__in=[
            Campaign.CampaignStatusEnum.ACTIVE.name,
            Campaign.CampaignStatusEnum.PREVIEW.name,
        ]
    ).all()

    for campaign in active_campaigns:
        # create campaign employee instances if the employee's active
        # campaigns have changed (for instance, if we created an employee
        # in a group with an active campaign)
        CampaignEmployee.objects.get_or_create(campaign=campaign, employee=instance)


class OrderState:
    def __init__(self):
        self.previous_order_products = None
        self.previous_order_status = None


order_state = OrderState()  # Create an instance of OrderState


@receiver(pre_save, sender=Order)
def store_previous_order_instance(sender, instance, **kwargs):
    # Store the current instance before saving
    if instance.pk:
        order = Order.objects.filter(pk=instance.pk).first()
        if order:
            order_state.previous_order_products = list(order.orderproduct_set.all())
            order_state.previous_order_status = order.status
    else:
        order_state.previous_order_products = None
        order_state.previous_order_status = None


@receiver(post_save, sender=Order)
def update_order_product_quantities(sender, instance, created, **kwargs):
    if (
        not created
        and (
            order_state.previous_order_status != Order.OrderStatusEnum.CANCELLED.name
            and order_state.previous_order_status
            != Order.OrderStatusEnum.INCOMPLETE.name
        )
        and (
            instance.status == Order.OrderStatusEnum.CANCELLED.name
            or instance.status == Order.OrderStatusEnum.INCOMPLETE.name
        )
    ):
        transaction.on_commit(
            lambda: _update_order_product_quantities(instance, type='cancel')
        )

    elif (
        not created
        and (
            order_state.previous_order_status == Order.OrderStatusEnum.CANCELLED.name
            or order_state.previous_order_status
            == Order.OrderStatusEnum.INCOMPLETE.name
        )
        and (
            instance.status == Order.OrderStatusEnum.PENDING.name
            or instance.status == Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name
        )
    ):
        transaction.on_commit(
            lambda: _update_order_product_quantities(instance, type='pending')
        )
    elif not created:
        transaction.on_commit(lambda: _update_order_product_quantities(instance, ''))


def _update_order_product_quantities(instance, type):
    # Fetch the latest state of the order products after save
    order = Order.objects.filter(pk=instance.pk).first()

    if order:
        # Get all OrderProducts related to this order
        for order_product in order.orderproduct_set.all():
            # Find the previous order product instance
            previous_order_product = next(
                (
                    product
                    for product in order_state.previous_order_products
                    if product.product_id == order_product.product_id
                ),
                None,
            )

            if previous_order_product:
                # Calculate the difference in quantity
                quantity_difference = (
                    order_product.quantity - previous_order_product.quantity
                )
                if type == 'cancel':
                    order_product.product_id.product_id.product_quantity += (
                        previous_order_product.quantity
                    )
                    order_product.product_id.product_id.save(
                        update_fields=['product_quantity']
                    )
                elif type == 'pending':
                    order_product.product_id.product_id.product_quantity -= (
                        order_product.quantity
                    )
                    order_product.product_id.product_id.save(
                        update_fields=['product_quantity']
                    )
                else:
                    if order.status in [
                        Order.OrderStatusEnum.PENDING.name,
                        Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
                    ]:
                        # If the quantity has increased, adjust the stock
                        if quantity_difference > 0:
                            order_product.product_id.product_id.product_quantity -= (
                                quantity_difference
                            )
                            order_product.product_id.product_id.save(
                                update_fields=['product_quantity']
                            )
                        # If the quantity has decreased,
                        # you may want to handle restocking logic here
                        elif quantity_difference < 0:
                            order_product.product_id.product_id.product_quantity += abs(
                                quantity_difference
                            )
                            order_product.product_id.product_id.save(
                                update_fields=['product_quantity']
                            )
            else:
                # Handle new products in the order
                if order.status in [
                    Order.OrderStatusEnum.PENDING.name,
                    Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
                ]:
                    order_product.product_id.product_id.product_quantity -= (
                        order_product.quantity
                    )
                    order_product.product_id.product_id.save(
                        update_fields=['product_quantity']
                    )
