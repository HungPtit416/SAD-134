from django.urls import path

from .views import charge, list_payments, ping, vnpay_create, vnpay_return

urlpatterns = [
    path("ping/", ping),
    path("payments/", list_payments),
    path("payments/charge/", charge),
    path("payments/vnpay/create/", vnpay_create),
    path("payments/vnpay/return/", vnpay_return),
]

