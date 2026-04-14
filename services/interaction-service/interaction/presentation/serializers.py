from rest_framework import serializers

from ..infrastructure.models import Event


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "user_id",
            "session_id",
            "event_type",
            "product_id",
            "query",
            "metadata",
            "created_at",
        ]


class CreateEventSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=64)
    session_id = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)
    event_type = serializers.CharField(max_length=64)
    product_id = serializers.IntegerField(required=False, allow_null=True)
    query = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    metadata = serializers.JSONField(required=False)

