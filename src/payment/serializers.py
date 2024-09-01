from rest_framework import serializers

from payment.models import PaymentInformation


class PaymentInformationSerializer(serializers.ModelSerializer):
    lang = serializers.CharField()

    class Meta:
        model = PaymentInformation
        fields = ('amount', 'lang')

    def get_lang(self, obj):
        return obj.lang


class PaymentDataSerializer(serializers.Serializer):
    asmachta = serializers.CharField(max_length=255)
    transactionId = serializers.CharField(max_length=255)
    transactionToken = serializers.CharField(max_length=255)
    processId = serializers.CharField(max_length=255)
    processToken = serializers.CharField(max_length=255)
