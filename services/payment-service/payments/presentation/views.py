from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import urllib.parse

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..infrastructure.models import Payment
from .serializers import ChargeRequestSerializer, PaymentSerializer, VnpayCreateRequestSerializer


@api_view(["GET"])
def ping(request):
    return Response({"ok": True, "service": "payment-service"})


@api_view(["GET"])
def list_payments(request):
    user_id = request.query_params.get("user_id")
    qs = Payment.objects.all()
    if user_id:
        qs = qs.filter(user_id=user_id)
    return Response(PaymentSerializer(list(qs[:200]), many=True).data)


@api_view(["POST"])
def charge(request):
    """
    Mock charge endpoint: always succeeds and returns a CAPTURED payment.
    """

    ser = ChargeRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user_id = ser.validated_data["user_id"]
    order_id = int(ser.validated_data["order_id"])
    amount = Decimal(str(ser.validated_data["amount"]))
    currency = (ser.validated_data.get("currency") or "USD").strip().upper()[:3]

    # "Capture" immediately for demo
    p = Payment.objects.create(
        user_id=user_id,
        order_id=order_id,
        amount=amount,
        currency=currency,
        status="CAPTURED",
        provider="mock",
        reference=f"PAY-{order_id}-{pseudoref(order_id)}",
    )
    return Response(PaymentSerializer(p).data, status=status.HTTP_201_CREATED)


def _vnpay_sign(params: dict[str, str]) -> str:
    # VNPAY requires SHA512 HMAC over sorted querystring (without vnp_SecureHash).
    items = sorted((k, v) for k, v in params.items() if v is not None and v != "" and k != "vnp_SecureHash")
    qs = "&".join([f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in items])
    secret = (settings.VNPAY_HASH_SECRET or "").encode("utf-8")
    return hmac.new(secret, qs.encode("utf-8"), hashlib.sha512).hexdigest()


def _vnpay_build_payment_url(*, order_id: int, amount_vnd: Decimal, order_info: str, ip_addr: str | None = None) -> tuple[str, str]:
    if not settings.VNPAY_TMN_CODE or not settings.VNPAY_HASH_SECRET:
        raise RuntimeError("VNPAY is not configured (missing VNPAY_TMN_CODE / VNPAY_HASH_SECRET).")

    now = datetime.now(timezone.utc) + timedelta(hours=7)  # VN time
    exp = now + timedelta(minutes=15)
    txn_ref = f"{order_id}-{now.strftime('%Y%m%d%H%M%S')}"
    params: dict[str, str] = {
        "vnp_Version": "2.1.0",
        "vnp_Command": "pay",
        "vnp_TmnCode": settings.VNPAY_TMN_CODE,
        "vnp_Amount": str(int(amount_vnd * 100)),  # x100
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": order_info[:255],
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_ReturnUrl": settings.VNPAY_RETURN_URL,
        "vnp_IpAddr": ip_addr or "127.0.0.1",
        "vnp_CreateDate": now.strftime("%Y%m%d%H%M%S"),
        "vnp_ExpireDate": exp.strftime("%Y%m%d%H%M%S"),
    }
    secure_hash = _vnpay_sign(params)
    params["vnp_SecureHash"] = secure_hash
    query = urllib.parse.urlencode(params)
    return txn_ref, f"{settings.VNPAY_PAYMENT_URL}?{query}"


@api_view(["POST"])
def vnpay_create(request):
    """
    Create a VNPAY payment URL (sandbox) and persist a PENDING payment row.
    Frontend should redirect browser to payment_url.
    """

    ser = VnpayCreateRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user_id = ser.validated_data["user_id"]
    order_id = int(ser.validated_data["order_id"])
    amount = Decimal(str(ser.validated_data["amount"]))
    currency = (ser.validated_data.get("currency") or "VND").strip().upper()[:3]
    info = (ser.validated_data.get("order_info") or f"Order {order_id}").strip()

    if currency != "VND":
        return Response({"detail": "VNPAY demo expects VND currency."}, status=status.HTTP_400_BAD_REQUEST)

    txn_ref, url = _vnpay_build_payment_url(order_id=order_id, amount_vnd=amount, order_info=info, ip_addr=request.META.get("REMOTE_ADDR"))

    p = Payment.objects.create(
        user_id=user_id,
        order_id=order_id,
        amount=amount,
        currency=currency,
        status="PENDING",
        provider="vnpay",
        reference=txn_ref,
    )
    return Response({"payment_id": p.id, "payment_url": url, "txn_ref": txn_ref}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def vnpay_return(request):
    """
    Verify VNPAY return query params and mark payment as CAPTURED/FAILED.
    """

    params = dict(request.query_params.items())
    secure_hash = params.get("vnp_SecureHash") or ""
    if not secure_hash:
        return Response({"detail": "Missing vnp_SecureHash"}, status=status.HTTP_400_BAD_REQUEST)

    expect = _vnpay_sign(params)
    if expect.lower() != secure_hash.lower():
        return Response({"detail": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

    txn_ref = params.get("vnp_TxnRef") or ""
    rsp = params.get("vnp_ResponseCode") or ""
    # Find latest payment with this reference
    p = Payment.objects.filter(provider="vnpay", reference=txn_ref).order_by("-id").first()
    if not p:
        return Response({"detail": "Payment not found", "txn_ref": txn_ref}, status=status.HTTP_404_NOT_FOUND)

    if rsp == "00":
        p.status = "CAPTURED"
    else:
        p.status = "FAILED"
    p.save(update_fields=["status"])

    return Response(
        {
            "ok": rsp == "00",
            "status": p.status,
            "payment_id": p.id,
            "order_id": p.order_id,
            "txn_ref": txn_ref,
            "vnp_ResponseCode": rsp,
        }
    )


def pseudoref(order_id: int) -> str:
    # deterministic short ref for report screenshots
    s = hex((order_id * 2654435761) & 0xFFFFFFFF)[2:]
    return s[-8:].upper()

