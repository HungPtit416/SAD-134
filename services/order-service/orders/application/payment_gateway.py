import os
from typing import Any

import requests


def charge_payment(*, user_id: str, order_id: int, amount: str, currency: str) -> dict[str, Any]:
    base = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:8008").rstrip("/")
    resp = requests.post(
        f"{base}/api/payments/charge/",
        json={"user_id": user_id, "order_id": int(order_id), "amount": str(amount), "currency": str(currency)},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def create_vnpay_payment(*, user_id: str, order_id: int, amount: str, currency: str, order_info: str | None = None) -> dict[str, Any]:
    base = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:8008").rstrip("/")
    payload: dict[str, Any] = {"user_id": user_id, "order_id": int(order_id), "amount": str(amount), "currency": str(currency)}
    if order_info:
        payload["order_info"] = str(order_info)
    resp = requests.post(f"{base}/api/payments/vnpay/create/", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def verify_vnpay_return(*, query_params: dict[str, Any]) -> dict[str, Any]:
    """
    Calls payment-service to verify VNPAY return signature and update payment status.
    """

    base = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:8008").rstrip("/")
    resp = requests.get(f"{base}/api/payments/vnpay/return/", params=query_params, timeout=10)
    resp.raise_for_status()
    return resp.json()

