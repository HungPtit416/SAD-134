from rest_framework import serializers

from ..infrastructure.models import Shipment


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = ["id", "user_id", "order_id", "status", "carrier", "tracking_code", "address", "created_at"]


class CreateShipmentRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=64)
    order_id = serializers.IntegerField(min_value=1)
    address = serializers.CharField(required=False, allow_blank=True, allow_null=True)

