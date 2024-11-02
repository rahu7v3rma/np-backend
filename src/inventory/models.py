from enum import Enum
import uuid

from django.core.validators import validate_email
from django.db import models
from django.db.models.functions import Cast, Round

from campaign.models import OrderProduct, QuickOfferOrderProduct
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

    class ProductTypeEnum(Enum):
        REGULAR = 'Regular'
        LARGE_PRODUCT = 'Large product'
        SENT_BY_SUPPLIER = 'Sent by supplier'

    class OfferTypeEnum(Enum):
        SPECIAL_OFFER = 'Special Offer'
        BEST_VALUE = 'Best Value'
        LIMITED_TIME_OFFER = 'Limited Time Offer'
        JUST_LANDED = 'Just Landed'
        STAFF_PICK = 'Staff Pick'

    brand = models.ForeignKey(
        'Brand', on_delete=models.CASCADE, related_name='brand_products'
    )
    supplier = models.ForeignKey(
        'Supplier', on_delete=models.CASCADE, related_name='supplier_products'
    )
    reference = models.CharField(max_length=100, null=True, blank=True)
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
    sku = models.CharField(max_length=255, unique=True)
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
                        product_type__in=(
                            ProductTypeEnum.LARGE_PRODUCT.name,
                            ProductTypeEnum.SENT_BY_SUPPLIER.name,
                        ),
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
    offer = models.CharField(
        max_length=20,
        choices=[(o.name, o.value) for o in OfferTypeEnum],
        blank=True,
        null=True,
        default=None,
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
        quantity = OrderProduct.objects.filter(product_id__product_id=self).aggregate(
            models.Sum('quantity')
        )
        quick_offer = QuickOfferOrderProduct.objects.filter(product_id=self).aggregate(
            models.Sum('quantity')
        )

        quantity = quantity.get('quantity__sum') or 0
        quick_offer = quick_offer.get('quantity__sum') or 0
        return quantity + quick_offer

    @property
    def remaining_quantity(self):
        return max(0, self.product_quantity - self.ordered_quantity)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100)
    icon_image = RandomNameImageFieldSVG(null=True, blank=True)
    order = models.PositiveIntegerField(null=True, blank=True, default=0)

    class Meta:
        verbose_name_plural = 'Categories'

    def __str__(self) -> str:
        return self.name


class CategoryProduct(models.Model):
    category_id = models.ForeignKey(Category, on_delete=models.CASCADE)
    product_id = models.ForeignKey(Product, on_delete=models.CASCADE)


class Tag(models.Model):
    name = models.CharField(max_length=100)

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
    name = models.CharField(max_length=100)
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
