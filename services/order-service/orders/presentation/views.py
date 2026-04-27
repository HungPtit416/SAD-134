from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..application.cart_gateway import clear_cart, fetch_cart
from ..application.inventory_gateway import release_stock
from ..application.payment_gateway import create_vnpay_payment, verify_vnpay_return
from ..application.shipping_gateway import create_shipment
from ..infrastructure.models import Order, OrderItem
from .serializers import CheckoutStartSerializer, OrderSerializer


def _get_user_id(request) -> str | None:
    qp = request.query_params.get("user_id")
    hdr = request.headers.get("X-User-Id")
    if qp and hdr and qp != hdr:
        raise PermissionDenied("user_id does not match authenticated user")
    return hdr or qp


def _cancel_if_expired(order: Order) -> bool:
    """
    Cancel unpaid orders after 5 minutes and release reserved inventory.
    Returns True if cancelled in this call.
    """

    if order.payment_status != "PENDING":
        return False
    if order.status not in {"PENDING_PAYMENT", "CREATED"}:
        return False
    if not order.created_at:
        return False
    if timezone.now() - order.created_at <= timedelta(minutes=5):
        return False

    # Release inventory only if it was reserved via cart.
    if getattr(order, "inventory_status", "PENDING") == "RESERVED":
        for it in order.items.all():
            try:
                release_stock(int(it.product_id), int(it.quantity))
            except Exception:  # noqa: BLE001
                pass
        order.inventory_status = "RELEASED"

    order.payment_status = "CANCELLED"
    order.status = "CANCELLED"
    order.save(update_fields=["payment_status", "status", "inventory_status"])
    return True


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer

    def get_queryset(self):
        user_id = _get_user_id(self.request)
        qs = Order.objects.prefetch_related("items").all()
        if user_id:
            qs = qs.filter(user_id=user_id)
        # Best-effort cleanup of expired pending orders (no cron needed for MVP).
        for o in list(qs.filter(payment_status="PENDING", status="PENDING_PAYMENT")[:50]):
            _cancel_if_expired(o)
        return qs


@api_view(["POST"])
def order_pay(request, order_id: int):
    """
    Create a new VNPAY payment_url for an existing order that is not captured yet.
    """

    user_id = _get_user_id(request)
    if not user_id:
        return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        order = Order.objects.prefetch_related("items").get(id=int(order_id), user_id=user_id)
    except Order.DoesNotExist:
        return Response({"detail": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

    _cancel_if_expired(order)
    order.refresh_from_db()
    if order.status == "CANCELLED":
        return Response({"detail": "Order was cancelled due to timeout", "order": OrderSerializer(order).data}, status=status.HTTP_400_BAD_REQUEST)

    if order.payment_status == "CAPTURED":
        return Response({"detail": "Order already paid", "order": OrderSerializer(order).data}, status=status.HTTP_400_BAD_REQUEST)

    try:
        pay = create_vnpay_payment(
            user_id=user_id,
            order_id=int(order.id),
            amount=str(order.total_amount),
            currency=str(order.currency),
            order_info=f"ElecShop order #{order.id}",
        )
        order.payment_id = int(pay.get("payment_id")) if pay.get("payment_id") is not None else None
        order.payment_status = "PENDING"
        order.status = "PENDING_PAYMENT"
        order.save(update_fields=["payment_id", "payment_status", "status"])
        return Response({"order": OrderSerializer(order).data, "payment_url": pay.get("payment_url")}, status=status.HTTP_201_CREATED)
    except Exception as e:  # noqa: BLE001
        return Response({"detail": f"Payment start failed: {e}", "order": OrderSerializer(order).data}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["POST"])
def checkout_start(request):
    user_id = _get_user_id(request)
    if not user_id:
        return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)

    ser = CheckoutStartSerializer(data=request.data or {})
    ser.is_valid(raise_exception=True)
    shipping_address = ser.validated_data.get("shipping_address") or {}
    shipping_method = (ser.validated_data.get("shipping_method") or "").strip().upper()[:32]

    cart = fetch_cart(user_id)
    items = cart.get("items", [])
    if not items:
        return Response({"detail": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

    currency = "VND"
    total = Decimal("0")
    shipping_fee = Decimal("0")
    # Minimal fee mapping (frontend can show rates; backend re-checks method).
    if shipping_method == "EXPRESS":
        shipping_fee = Decimal("60000")
    elif shipping_method == "SAME_DAY":
        shipping_fee = Decimal("120000")
    else:
        shipping_method = "STANDARD"
        shipping_fee = Decimal("30000")

    with transaction.atomic():
        order = Order.objects.create(
            user_id=user_id,
            status="PENDING_PAYMENT",
            currency=currency,
            total_amount=0,
            shipping_address=shipping_address,
            shipping_method=shipping_method,
            shipping_fee=shipping_fee,
            payment_status="PENDING",
            inventory_status="RESERVED",
            shipping_status="PENDING",
        )
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
        order.total_amount = total + shipping_fee
        order.save()

    try:
        # Clear cart but do NOT release reserved stock.
        try:
            clear_cart(user_id)
        except Exception:  # noqa: BLE001
            pass
        pay = create_vnpay_payment(
            user_id=user_id,
            order_id=int(order.id),
            amount=str(order.total_amount),
            currency=str(order.currency),
            order_info=f"ElecShop order #{order.id}",
        )
        order.payment_id = int(pay.get("payment_id")) if pay.get("payment_id") is not None else None
        order.save(update_fields=["payment_id"])
        return Response({"order": OrderSerializer(order).data, "payment_url": pay.get("payment_url")}, status=status.HTTP_201_CREATED)
    except Exception as e:  # noqa: BLE001
        order.payment_status = "FAILED"
        order.save(update_fields=["payment_status"])
        return Response({"detail": f"Payment start failed: {e}", "order": OrderSerializer(order).data}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET"])
def checkout_confirm(request):
    """
    Called by frontend after VNPAY redirect to /payment-return.
    It verifies signature via payment-service, then creates shipment + clears cart.
    """

    user_id = _get_user_id(request)
    if not user_id:
        return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)

    # Verify with payment-service (signature + status update)
    try:
        raw = dict(request.query_params.items())
        # Only forward VNPAY params; do not include user_id or other app params
        vnp_params = {k: v for k, v in raw.items() if k.startswith("vnp_")}
        verified = verify_vnpay_return(query_params=vnp_params)
    except Exception as e:  # noqa: BLE001
        return Response({"detail": f"Verify failed: {e}"}, status=status.HTTP_400_BAD_REQUEST)

    order_id = int(verified.get("order_id") or 0)
    if order_id <= 0:
        return Response({"detail": "Missing order_id in verification result"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        order = Order.objects.prefetch_related("items").get(id=order_id, user_id=user_id)
    except Order.DoesNotExist:
        return Response({"detail": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

    _cancel_if_expired(order)
    order.refresh_from_db()
    if order.status == "CANCELLED":
        return Response({"ok": False, "detail": "Order was cancelled due to timeout", "order": OrderSerializer(order).data}, status=status.HTTP_200_OK)

    if not verified.get("ok"):
        order.payment_status = "FAILED"
        order.status = "PAYMENT_FAILED"
        order.save(update_fields=["payment_status", "status"])
        return Response({"ok": False, "order": OrderSerializer(order).data}, status=status.HTTP_200_OK)

    order.payment_status = "CAPTURED"
    order.status = "PAID"
    order.save(update_fields=["payment_status", "status"])

    # Create shipment after successful payment
    try:
        ship = create_shipment(user_id=user_id, order_id=int(order.id), address=str(order.shipping_address or ""))
        order.shipping_status = str(ship.get("status") or "CREATED")
        order.shipment_id = int(ship.get("id")) if ship.get("id") is not None else None
        order.tracking_code = str(ship.get("tracking_code") or "")[:64]
        order.status = "SHIPPING_CREATED"
        order.save(update_fields=["shipping_status", "shipment_id", "tracking_code", "status"])
    except Exception as e:  # noqa: BLE001
        order.shipping_status = "FAILED"
        order.save(update_fields=["shipping_status"])
        return Response({"ok": True, "detail": f"Shipping failed: {e}", "order": OrderSerializer(order).data}, status=status.HTTP_200_OK)

    return Response({"ok": True, "order": OrderSerializer(order).data}, status=status.HTTP_200_OK)

