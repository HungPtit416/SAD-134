from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .auth import register
from .staff_auth import StaffTokenObtainPairView
from .views import CustomerViewSet, ping, verify_jwt

router = DefaultRouter()
router.register(r"customers", CustomerViewSet, basename="customer")

urlpatterns = [
    path("ping/", ping),
    path("auth/verify/", verify_jwt),
    path("auth/register/", register),
    path("auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/staff/login/", StaffTokenObtainPairView.as_view(), name="staff_token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("", include(router.urls)),
]

