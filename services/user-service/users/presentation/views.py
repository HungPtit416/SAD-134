from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ..infrastructure.models import Customer
from .serializers import CustomerSerializer


@api_view(["GET"])
def ping(_request):
    return Response({"status": "ok"})


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer


@api_view(["GET"])
def verify_jwt(request):
    """
    Lightweight auth check for the API Gateway (Nginx auth_request).
    - Reads Authorization: Bearer <token>
    - Returns 200 if valid, else 401
    """

    auth = JWTAuthentication()
    try:
        user_auth = auth.authenticate(request)
    except Exception:  # noqa: BLE001
        user_auth = None
    if not user_auth:
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    user, _token = user_auth
    username = getattr(user, "username", None)
    resp = Response({"ok": True, "user": username}, status=status.HTTP_200_OK)
    if username:
        resp["X-User-Id"] = str(username)
    # Role hints for the API Gateway to forward downstream.
    # We reuse Django's built-in flags (no custom user model needed).
    is_staff = bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
    resp["X-User-Role"] = "staff" if is_staff else "customer"
    return resp

