from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class StaffTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        is_staff = bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
        if not is_staff:
            # Keep message simple; frontend maps HTTP codes to Vietnamese text.
            raise AuthenticationFailed("Staff only")
        return data


class StaffTokenObtainPairView(TokenObtainPairView):
    serializer_class = StaffTokenObtainPairSerializer

