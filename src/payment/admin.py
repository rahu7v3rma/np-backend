from django.contrib import admin

from payment.models import PaymentInformation


@admin.register(PaymentInformation)
class PaymentInformationAdmin(admin.ModelAdmin):
    pass
