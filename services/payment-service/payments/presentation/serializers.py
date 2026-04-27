from rest_framework import serializers

from ..infrastructure.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "user_id", "order_id", "amount", "currency", "status", "provider", "reference", "created_at"]


class ChargeRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=64)
    order_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)


class VnpayCreateRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=64)
    order_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)
    order_info = serializers.CharField(required=False, allow_blank=True, allow_null=True)


