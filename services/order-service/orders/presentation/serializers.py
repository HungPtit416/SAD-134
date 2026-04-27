from rest_framework import serializers

from ..infrastructure.models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "product_id", "quantity", "unit_price", "currency"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user_id",
            "status",
            "payment_status",
            "payment_id",
            "inventory_status",
            "shipping_status",
            "shipment_id",
            "tracking_code",
            "shipping_address",
            "shipping_method",
            "shipping_fee",
            "currency",
            "total_amount",
            "created_at",
            "items",
        ]


class CheckoutStartSerializer(serializers.Serializer):
    shipping_address = serializers.JSONField(required=False)
    shipping_method = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=32)

