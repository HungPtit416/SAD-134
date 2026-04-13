from rest_framework import serializers

from ..infrastructure.models import StockItem


class StockItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockItem
        fields = ["id", "product_id", "initial_quantity", "quantity", "updated_at"]

