from django.contrib.auth.models import User as AuthUser
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..infrastructure.models import Role, User as AppUser


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=6, write_only=True)
    full_name = serializers.CharField(required=False, allow_blank=True)


@api_view(["POST"])
def register(request):
    ser = RegisterSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    email = ser.validated_data["email"].lower().strip()
    password = ser.validated_data["password"]
    full_name = ser.validated_data.get("full_name", "")

    if AuthUser.objects.filter(username=email).exists():
        return Response({"detail": "Email already registered"}, status=status.HTTP_409_CONFLICT)

    user = AuthUser.objects.create_user(username=email, email=email, password=password, first_name=full_name)
    # Create business-profile record for downstream services
    role, _ = Role.objects.get_or_create(name="user", defaults={"description": "Default user role"})
    try:
        app_user = AppUser.objects.get(email=email)
        app_user.full_name = full_name
        app_user.role = role
        app_user.save()
    except AppUser.DoesNotExist:
        AppUser.objects.create(
            id=user.id,
            email=email,
            full_name=full_name,
            role=role,
        )
    return Response({"id": user.id, "email": user.email}, status=status.HTTP_201_CREATED)

