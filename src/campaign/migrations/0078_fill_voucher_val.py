from django.db import migrations


def fill_voucher_val(apps, schema_editor):
    OrderProduct = apps.get_model('campaign', 'OrderProduct')

    for op in OrderProduct.objects.filter(voucher_val__isnull=True):
        product = op.product_id
        if product.product_id.product_kind != 'MONEY':
            continue

        budget = product.employee_group_campaign_id.budget_per_employee
        if budget is None:
            continue

        if product.discount_mode == 'EMPLOYEE':
            rate = product.organization_discount_rate or 0
            try:
                voucher_val = round(budget / (1 - (rate / 100)), 1)
            except ZeroDivisionError:
                voucher_val = budget
        else:
            voucher_val = round(budget, 1)

        op.voucher_val = voucher_val
        op.save(update_fields=['voucher_val'])


class Migration(migrations.Migration):
    dependencies = [
        ('campaign', '0077_orderproduct_voucher_val'),
    ]

    operations = [
        migrations.RunPython(fill_voucher_val),
    ]
