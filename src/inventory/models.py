from enum import Enum
import uuid

from django.core.validators import MaxLengthValidator, MaxValueValidator, validate_email
from django.db import models
from django.db.models.functions import Cast, Round
from django.utils.translation import gettext_lazy as _

from campaign.models import Order, OrderProduct
from common.managers import ActiveObjectsManager
from common.models import BaseModelMixin
from lib.phone_utils import convert_phone_number_to_long_form, validate_phone_number
from lib.storage import RandomNameImageField, RandomNameImageFieldSVG
from logistics.models import LogisticsCenterStockSnapshotLine


class Product(models.Model):
    class ProductKindEnum(Enum):
        PHYSICAL = 'physical'
        MONEY = 'money'
        BUNDLE = 'bundle'
        VARIATION = 'variation'

    class ProductTypeEnum(Enum):
        REGULAR = _('Regular')
        LARGE_PRODUCT = _('Large product')
        SENT_BY_SUPPLIER = _('Sent by supplier')

    class OfferTypeEnum(Enum):
        SPECIAL_OFFER = 'Special Offer'
        BEST_VALUE = 'Best Value'
        LIMITED_TIME_OFFER = 'Limited Time Offer'
        JUST_LANDED = 'Just Landed'
        STAFF_PICK = 'Staff Pick'

    class VoucherTypeEnum(Enum):
        PHYSICAL = 'physical'
        DIGITAL = 'digital'

    brand = models.ForeignKey(
        'Brand', on_delete=models.CASCADE, related_name='brand_products'
    )
    supplier = models.ForeignKey(
        'Supplier', on_delete=models.CASCADE, related_name='supplier_products'
    )
    # add max length as a validator so we don't enforce it on pre-existing products
    reference = models.CharField(
        max_length=100, null=True, blank=True, validators=[MaxLengthValidator(22)]
    )
    sale_price = models.IntegerField(null=True, blank=True)
    name = models.CharField(max_length=100)
    product_kind = models.CharField(
        max_length=20,
        choices=[
            (product_kind.name, product_kind.value) for product_kind in ProductKindEnum
        ],
    )
    product_type = models.CharField(
        max_length=20,
        choices=[
            (product_type.name, product_type.value) for product_type in ProductTypeEnum
        ],
    )
    product_quantity = models.IntegerField(default=2147483647, null=False, blank=False)
    description = models.TextField()
    # add max length as a validator so we don't enforce it on pre-existing products
    sku = models.CharField(
        max_length=255, unique=True, validators=[MaxLengthValidator(22)]
    )
    link = models.TextField(null=True, blank=True)
    active = models.BooleanField(default=True)
    cost_price = models.IntegerField()
    # total_cost is calculated with a generated field to ease using it in
    # queries (for export for example). the formula is:
    # cost_price
    # * if logistics_rate_cost_percent
    #   then (1 + logistics_rate_cost_percent / 100)
    #   else 1
    # + if product_type in (LARGE_PRODUCT, SENT_BY_SUPPLIER)
    #   then delivery_price
    #   else 0
    total_cost = models.GeneratedField(
        expression=Round(
            Cast('cost_price', output_field=models.FloatField())
            * models.Case(
                models.When(
                    models.Q(logistics_rate_cost_percent__isnull=True),
                    then=models.Value(1.0),
                ),
                default=(
                    models.Value(1.0)
                    + Cast(
                        'logistics_rate_cost_percent', output_field=models.FloatField()
                    )
                    / models.Value(100.0)
                ),
            )
            + models.Case(
                models.When(
                    models.Q(
                        delivery_price__isnull=False,
                    ),
                    then=Cast('delivery_price', output_field=models.FloatField()),
                ),
                default=models.Value(0.0),
            ),
            precision=1,
        ),
        output_field=models.FloatField(),
        db_persist=True,
    )
    delivery_price = models.IntegerField(null=True, blank=True)
    logistics_rate_cost_percent = models.IntegerField(null=True, blank=True)
    google_price = models.IntegerField(null=True, blank=True)
    technical_details = models.TextField(null=True, blank=True)
    warranty = models.TextField(null=True, blank=True)
    exchange_value = models.IntegerField(null=True, blank=True)
    exchange_policy = models.TextField(null=True, blank=True)
    categories = models.ManyToManyField('Category', through='CategoryProduct')
    tags = models.ManyToManyField('Tag', through='TagProduct')
    alert_stock_sent = models.BooleanField(default=False)
    logistics_snapshot_stock_line = models.ForeignKey(
        LogisticsCenterStockSnapshotLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    bundled_products = models.ManyToManyField('Product', through='ProductBundleItem')
    variations = models.ManyToManyField(
        'Variation', through='ProductVariation', related_name='products'
    )
    offer = models.CharField(
        max_length=20,
        choices=[(o.name, o.value) for o in OfferTypeEnum],
        blank=True,
        null=True,
        default=None,
    )
    voucher_type = models.CharField(
        max_length=20,
        choices=[
            (voucher_type.name, voucher_type.value) for voucher_type in VoucherTypeEnum
        ],
        blank=True,
        null=True,
    )
    client_discount_rate = models.FloatField(
        blank=True,
        null=True,
        validators=[MaxValueValidator(100.0)],
        help_text='Enter a Client Discount Rate up to 100.0.',
    )
    supplier_discount_rate = models.FloatField(
        blank=True,
        null=True,
        validators=[MaxValueValidator(100.0)],
        help_text='Enter a Supplier Discount Rate up to 100.0.',
    )

    def update_bundle_calculated_fields(self):
        if self.product_kind == Product.ProductKindEnum.BUNDLE.name:
            bundled_items = self.bundled_items.all()
            self.supplier = bundled_items[0].product.supplier
            self.brand = bundled_items[0].product.brand
            self.sku = ','.join(
                [f'{bi.product.sku}|{bi.quantity}' for bi in bundled_items]
            )
            self.cost_price = sum(
                [bi.product.cost_price * bi.quantity for bi in bundled_items]
            )
            self.delivery_price = sum(
                [(bi.product.delivery_price or 0) * bi.quantity for bi in bundled_items]
            )
            self.sale_price = sum(
                [(bi.product.sale_price or 0) * bi.quantity for bi in bundled_items]
            )
            self.google_price = sum(
                [(bi.product.google_price or 0) * bi.quantity for bi in bundled_items]
            )
            self.save(
                update_fields=[
                    'supplier',
                    'brand',
                    'sku',
                    'cost_price',
                    'delivery_price',
                    'sale_price',
                    'google_price',
                ]
            )
        else:
            # remove all bundled items if this is not a bundle (may have been
            # changed now)
            self.bundled_items.all().delete()

    @property
    def main_image(self):
        return self.images.filter(main=True).first()

    @property
    def main_image_link(self):
        main_image = self.images.filter(main=True).first()
        if main_image:
            return main_image.image.url
        return None

    @property
    def ordered_quantity(self):
        quantity = OrderProduct.objects.filter(
            product_id__product_id=self,
            order_id__status__in=[
                Order.OrderStatusEnum.PENDING.name,
                Order.OrderStatusEnum.SENT_TO_LOGISTIC_CENTER.name,
            ],
        ).aggregate(models.Sum('quantity'))

        return quantity.get('quantity__sum') or 0

    @property
    def remaining_quantity(self):
        return max(0, self.product_quantity - self.ordered_quantity)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    icon_image = RandomNameImageFieldSVG(null=True, blank=True)
    order = models.IntegerField(
        null=True,
        blank=True,
        default=0,
        help_text=(
            'Use positive values normally. Negative values will cause the '
            'category to be displayed before the "All" category'
        ),
    )

    class Meta:
        verbose_name_plural = 'Categories'

    def __str__(self) -> str:
        return self.name


class CategoryProduct(models.Model):
    category_id = models.ForeignKey(Category, on_delete=models.CASCADE)
    product_id = models.ForeignKey(Product, on_delete=models.CASCADE)


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self) -> str:
        return self.name


class TagProduct(models.Model):
    tag_id = models.ForeignKey(Tag, on_delete=models.CASCADE)
    product_id = models.ForeignKey(Product, on_delete=models.CASCADE)


class ProductBundleItem(models.Model):
    # the bundle product - Product of kind BUNDLE
    bundle = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='bundled_items'
    )
    # the bundled product - any Product included in the bundle
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='bundles'
    )
    # how many times the bundled product is included in the bundle
    quantity = models.PositiveIntegerField()


class Brand(BaseModelMixin):
    name = models.CharField(max_length=100, unique=True)
    logo_image = RandomNameImageField(null=True, blank=True)
    suppliers = models.ManyToManyField('Supplier', through='BrandSupplier')

    objects = ActiveObjectsManager()
    all_objects = models.Manager()

    def __str__(self) -> str:
        return self.name


class Supplier(BaseModelMixin):
    name = models.CharField(max_length=100)
    house_number = models.PositiveIntegerField(null=True, blank=True)
    address_city = models.CharField(max_length=255, null=True, blank=True)
    address_street = models.CharField(max_length=255, null=True, blank=True)
    address_street_number = models.CharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=255, validators=[validate_email])
    phone_number = models.CharField(
        max_length=255, null=True, blank=True, validators=[validate_phone_number]
    )
    brands = models.ManyToManyField('Brand', through='BrandSupplier')

    objects = ActiveObjectsManager()
    all_objects = models.Manager()

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if self.phone_number:
            fromatted_phone_number = convert_phone_number_to_long_form(
                self.phone_number
            )

            if fromatted_phone_number:
                self.phone_number = fromatted_phone_number
            else:
                raise Exception(f'Invalid phone number: {self.phone_number}')

        return super().save(*args, **kwargs)


class BrandSupplier(models.Model):
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='images'
    )
    main = models.BooleanField(default=False)
    image = RandomNameImageField()

    def save(self, *args, **kwargs):
        if not self.product.images.exists():
            self.main = True
            return super().save(*args, **kwargs)

        if self.main:
            self.product.images.update(main=False)

        return super().save(*args, **kwargs)

    def __str__(self):
        return self.image.url


class ShareTypeEnum(Enum):
    Product = 'Product'
    Cart = 'Cart'

    @classmethod
    def choices(cls):
        return [(choice.name, choice.value) for choice in cls]


class Share(models.Model):
    from campaign.models import Employee, QuickOffer

    share_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    share_type = models.CharField(
        max_length=20, choices=ShareTypeEnum.choices(), verbose_name='Share Type'
    )

    owner = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='product_shares',
        verbose_name='Owner',
        null=True,
        blank=True,
    )

    campaign_code = models.CharField(
        max_length=155, verbose_name='Campaign Code', null=True, blank=True
    )
    quick_offer = models.ForeignKey(
        QuickOffer, on_delete=models.CASCADE, null=True, blank=True
    )

    products = models.ManyToManyField(
        'Product', related_name='shares', verbose_name='Products'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')

    def __str__(self):
        return f'{self.share_type} - {self.share_id}'

    class Meta:
        verbose_name = 'Share'
        verbose_name_plural = 'Shares'
        ordering = ['-created_at']


class Variation(models.Model):
    class VariationKindEnum(Enum):
        TEXT = 'text'
        COLOR = 'color'

    variation_kind = models.CharField(
        max_length=10,
        choices=[(vk.name, vk.value) for vk in VariationKindEnum],
    )
    system_name = models.CharField(max_length=255)
    site_name = models.CharField(max_length=255)
    color_variation = models.ManyToManyField(
        'ColorVariation', blank=True, related_name='variations'
    )
    text_variation = models.ManyToManyField(
        'TextVariation', blank=True, related_name='text_variations'
    )

    def __str__(self):
        return self.system_name


class ColorVariation(models.Model):
    name = models.CharField(max_length=30)
    color_code = models.CharField(max_length=10)

    def __str__(self):
        return self.name


class TextVariation(models.Model):
    text = models.CharField(max_length=255)

    def __str__(self):
        return self.text


class ProductVariation(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variation = models.ForeignKey(Variation, on_delete=models.CASCADE)
    is_enabled = models.BooleanField(default=True)

    # class Meta:
    #     unique_together = ('product', 'variation')

    def __str__(self):
        return self.variation.system_name

    def save(self, *args, **kwargs):
        total_existing_count = ProductVariation.objects.filter(
            product=self.product
        ).count()
        if total_existing_count >= 5:
            raise ValueError(
                f'Product {self.product.name} can only have up to 5 variations.'
            )
        return super().save(*args, **kwargs)


class ProductColorVariationImage(models.Model):
    product_variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='color_variations'
    )
    variation = models.ForeignKey(Variation, on_delete=models.CASCADE)
    color = models.ForeignKey(ColorVariation, on_delete=models.CASCADE)
    image = RandomNameImageField(null=True, blank=True)

    def __str__(self):
        return f'{self.id}'


class ProductTextVariation(models.Model):
    product_variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='text_variations'
    )
    variation = models.ForeignKey(Variation, on_delete=models.CASCADE)
    text = models.ForeignKey(TextVariation, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.id}'
