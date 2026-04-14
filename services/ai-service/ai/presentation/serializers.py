from rest_framework import serializers


class RecommendationRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=64)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50)


class ChatRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=64)
    message = serializers.CharField()

