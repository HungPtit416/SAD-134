from rest_framework import serializers


class RecommendationRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=64)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50)
    query = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    seed_product_ids = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ChatRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=64)
    message = serializers.CharField()

