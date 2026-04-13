from rest_framework import serializers

from ..infrastructure.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "user_id", "email", "full_name", "created_at"]

