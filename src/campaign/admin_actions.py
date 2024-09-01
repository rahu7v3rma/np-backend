from django.contrib import messages
from django.utils.translation import ngettext
from rest_framework.reverse import reverse as drf_reverse

from inventory.models import Product
from logistics.tasks import send_order_to_logistics_center

from .models import (
    Campaign,
    CampaignEmployee,
    Employee,
    EmployeeGroupCampaign,
    Order,
)
from .tasks import (
    export_orders_as_xlsx as export_orders_as_xlsx_task,
    send_campaign_welcome_messages,
)


class CampaignActionsMixin:
    def activate_campaign(self, request, queryset):
        # only pending campaigns should be activated
        pending_campaigns = queryset.filter(status='PENDING').all()

        for campaign in pending_campaigns:
            if request.POST.get('send_email') == '1':
                send_campaign_welcome_messages.apply_async((campaign.id,))

            for each in EmployeeGroupCampaign.objects.filter(campaign=campaign).all():
                employee = Employee.objects.filter(
                    employee_group=each.employee_group
                ).all()
                for emp in employee:
                    CampaignEmployee.objects.get_or_create(
                        campaign=campaign, employee=emp
                    )

        updated = pending_campaigns.update(status='ACTIVE')

        self.message_user(
            request,
            ngettext(
                '%d campaign was successfully marked as active.',
                '%d campaigns were successfully marked as active.',
                updated,
            )
            % updated,
            messages.SUCCESS,
        )

    def resend_invitation(self, request, queryset):
        # only active campaigns can be resent
        active_campaigns = queryset.filter(status='ACTIVE').all()

        for campaign in active_campaigns:
            send_campaign_welcome_messages.apply_async((campaign.id,))

        self.message_user(
            request,
            ngettext(
                "%d campaign's invitation was successfully resent.",
                "%d campaigns' invitatinos were successfully resent.",
                len(active_campaigns),
            )
            % len(active_campaigns),
            messages.SUCCESS,
        )

    def finish_campaign(self, request, queryset):
        updated = queryset.filter(status='ACTIVE').update(status='FINISHED')
        self.message_user(
            request,
            ngettext(
                '%d campaign was successfully marked as finished.',
                '%d campaigns were successfully marked as finished.',
                updated,
            )
            % updated,
            messages.SUCCESS,
        )

    def export_orders_as_xlsx(self, request, queryset):
        valid_campaigns = []

        for campaign in queryset:
            if campaign.status in ['ACTIVE', 'FINISHED']:
                valid_campaigns.append(campaign)

        # query only orders from the selected active or finished campaigns and
        # only pending orders
        orders_queryset = Order.objects.filter(
            campaign_employee_id__campaign__in=valid_campaigns,
            status=Order.OrderStatusEnum.PENDING.name,
        )

        # using the inner query since it can be pickled to recreate the
        # queryset (celery is in charge of pickling here), based on docs -
        # https://docs.djangoproject.com/en/5.1/ref/models/querysets/#pickling-querysets
        export_orders_as_xlsx_task.apply_async(
            (
                orders_queryset.query,
                request.user.pk,
                request.user.email,
                drf_reverse('download_export_file_view', request=request),
            )
        )

        self.message_user(
            request,
            (
                'Exporting campaign(s) orders, file will be sent to '
                f'"{request.user.email}" when ready'
            ),
            messages.SUCCESS,
        )


class OrderActionsMixin:
    def export_as_xlsx(self, request, queryset):
        # using the inner query since it can be pickled to recreate the
        # queryset (celery is in charge of pickling here), based on docs -
        # https://docs.djangoproject.com/en/5.1/ref/models/querysets/#pickling-querysets
        export_orders_as_xlsx_task.apply_async(
            (
                queryset.query,
                request.user.pk,
                request.user.email,
                drf_reverse('download_export_file_view', request=request),
            )
        )

        self.message_user(
            request,
            f'Exporting orders, file will be sent to "{request.user.email}" when ready',
            messages.SUCCESS,
        )

    def send_orders(self, request, queryset):
        scheduled_count = 0

        # validate all orders can be sent, otherwise fail the entire request
        errors = []
        for order in queryset.all():
            if order.status != Order.OrderStatusEnum.PENDING.name:
                errors.append(f'order {order.reference} status is not pending')
            if (
                order.campaign_employee_id.campaign.status
                != Campaign.CampaignStatusEnum.FINISHED.name
            ):
                errors.append(
                    f'order {order.reference} is part of a campaign that is '
                    'not finished'
                )

            for p in order.orderproduct_set.all():
                if (
                    p.product_id.product_id.product_type
                    == Product.ProductTypeEnum.SENT_BY_SUPPLIER.name
                ):
                    errors.append(
                        f'order {order.reference} has a product that is sent '
                        'by supplier'
                    )
                if (
                    p.product_id.product_id.product_kind
                    == Product.ProductKindEnum.MONEY.name
                ):
                    errors.append(f'order {order.reference} has a money product')

        if len(errors) > 0:
            errors_str = ', '.join(errors)

            self.message_user(
                request,
                f'Failed to send orders (none were sent): {errors_str}',
                messages.ERROR,
            )
            return

        for order in queryset.all():
            send_order_to_logistics_center.apply_async((order.pk,))
            scheduled_count += 1

        self.message_user(
            request,
            ngettext(
                '%d order was scheduled to be sent to the logistics center.',
                '%d orders were scheduled to be sent to the logistics center.',
                scheduled_count,
            )
            % scheduled_count,
            messages.SUCCESS,
        )
