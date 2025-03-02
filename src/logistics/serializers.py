from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from .models import (
    PurchaseOrder,
    PurchaseOrderProduct,
)


class PurchaseOrderProductSerializer(ModelSerializer):
    order = serializers.IntegerField(read_only=True)

    class Meta:
        model = PurchaseOrderProduct
        fields = '__all__'


class PurchaseOrderSerializer(ModelSerializer):
    products = PurchaseOrderProductSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = '__all__'
