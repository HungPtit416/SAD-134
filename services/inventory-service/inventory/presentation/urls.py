from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .actions import release_stock, reserve_stock, stock_by_products, upsert_stock
from .views import StockItemViewSet

router = DefaultRouter()
router.register(r"stock", StockItemViewSet, basename="stock")

urlpatterns = [
    path("stock/by-products/", stock_by_products),
    path("stock/upsert/", upsert_stock),
    path("stock/reserve/", reserve_stock),
    path("stock/release/", release_stock),
    path("", include(router.urls)),
]

