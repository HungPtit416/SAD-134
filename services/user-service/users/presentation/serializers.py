from rest_framework import serializers

from ..infrastructure.models import User


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "user_id", "email", "full_name", "role", "role_name", "created_at"]

    def get_role_name(self, obj):
        r = getattr(obj, "role", None)
        return getattr(r, "name", None)

