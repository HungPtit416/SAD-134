from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrderViewSet, checkout_confirm, checkout_start, order_pay

router = DefaultRouter()
router.register(r"orders", OrderViewSet, basename="order")

urlpatterns = [
    path("", include(router.urls)),
    path("checkout/start/", checkout_start),
    path("checkout/confirm/", checkout_confirm),
    path("orders/<int:order_id>/pay/", order_pay),
]

