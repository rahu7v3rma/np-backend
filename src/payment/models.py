from django.db import models

from campaign.models import Order


class PaymentInformation(models.Model):
    amount = models.IntegerField()
    process_id = models.IntegerField()
    process_token = models.CharField(max_length=255)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    payment_date = models.DateField(auto_now_add=True)
    transaction_id = models.CharField(
        max_length=255, null=True, blank=True, default=None
    )
    transaction_token = models.CharField(
        max_length=255, null=True, blank=True, default=None
    )
    asmachta = models.CharField(max_length=255, null=True, blank=True, default=None)
    is_paid = models.BooleanField(default=False)
