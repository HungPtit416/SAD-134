from django.urls import path

from .views import create_shipment, list_shipments, ping, rates, update_status

urlpatterns = [
    path("ping/", ping),
    path("rates/", rates),
    path("shipments/", list_shipments),
    path("shipments/create/", create_shipment),
    path("shipments/<int:shipment_id>/status/", update_status),
]

