from rest_framework.serializers import (
    CharField,
    IntegerField,
    ListField,
    ModelSerializer,
    Serializer,
    SerializerMethodField,
)

from campaign.models import Organization, OrganizationProduct
from campaign.serializers import TranslationSerializer

from .models import (
    Brand,
    Category,
    CategoryProduct,
    Product,
    ProductImage,
    Supplier,
    Tag,
)


class BrandSerializer(ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'


class SupplierSerializer(ModelSerializer):
    class Meta:
        model = Supplier
        fields = ('id', 'name', 'email')


class CategorySerializer(TranslationSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class TagSerializer(ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'


class ProductImageSerializer(ModelSerializer):
    class Meta:
        model = ProductImage
        fields = '__all__'


class OrganizationSerializer(ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name']


class OrganizationProductSerializer(ModelSerializer):
    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = OrganizationProduct
        fields = ['organization', 'price']


class ProductSerializer(ModelSerializer):
    brand = BrandSerializer(read_only=True)
    supplier = SupplierSerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    calculated_price = IntegerField(read_only=True)
    main_image_link = CharField()
    category = SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'images',
            'name',
            'category',
            'brand',
            'sku',
            'reference',
            'cost_price',
            'total_cost',
            'google_price',
            'supplier',
            'calculated_price',
            'main_image_link',
            'remaining_quantity',
        ]

    def get_category(self, obj: Product):
        first_category = obj.categories.all().first()
        return first_category.name if first_category else ''


class CategoryProductSerializer(ModelSerializer):
    class Meta:
        model = CategoryProduct
        fields = '__all__'


class ProductGetSerializer(Serializer):
    limit = IntegerField(required=False, min_value=1, max_value=200)
    page = IntegerField(required=False, min_value=1)
    organization_id = IntegerField(required=True)
    price_min = IntegerField(required=False)
    price_max = IntegerField(required=False)
    organization_price_min = IntegerField(required=False)
    organization_price_max = IntegerField(required=False)
    brand_id = IntegerField(required=False)
    supplier_id = IntegerField(required=False)
    category_id = IntegerField(required=False)
    tag_id = IntegerField(required=False)
    query = CharField(required=False)
    product_ids = ListField(child=IntegerField(), required=False)


class GetSupplierSerializer(ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['name']


class ProductSkuSearchSerializer(Serializer):
    q = CharField(max_length=255)
