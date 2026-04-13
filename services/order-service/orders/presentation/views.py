from decimal import Decimal

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..application.cart_gateway import clear_cart, fetch_cart
from ..infrastructure.models import Order, OrderItem
from .serializers import OrderSerializer


def _get_user_id(request) -> str | None:
    return request.query_params.get("user_id") or request.headers.get("X-User-Id")


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer

    def get_queryset(self):
        user_id = _get_user_id(self.request)
        qs = Order.objects.prefetch_related("items").all()
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs


@api_view(["POST"])
def checkout(request):
    user_id = _get_user_id(request)
    if not user_id:
        return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)

    cart = fetch_cart(user_id)
    items = cart.get("items", [])
    if not items:
        return Response({"detail": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

    currency = "USD"
    total = Decimal("0")

    with transaction.atomic():
        order = Order.objects.create(user_id=user_id, status="CREATED", currency=currency, total_amount=0)
        for it in items:
            unit_price = it.get("unit_price")
            if unit_price is None:
                return Response({"detail": "Missing unit_price in cart item"}, status=status.HTTP_400_BAD_REQUEST)
            qty = int(it["quantity"])
            currency = it.get("currency") or currency
            OrderItem.objects.create(
                order=order,
                product_id=int(it["product_id"]),
                quantity=qty,
                unit_price=Decimal(str(unit_price)),
                currency=currency,
            )
            total += Decimal(str(unit_price)) * qty
        order.currency = currency
        order.total_amount = total
        order.save()

    try:
        clear_cart(user_id)
    except Exception:  # noqa: BLE001
        pass

    return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

