import os
from typing import Any

import requests


def create_shipment(*, user_id: str, order_id: int, address: str | None = None) -> dict[str, Any]:
    base = os.environ.get("SHIPPING_SERVICE_URL", "http://localhost:8009").rstrip("/")
    payload: dict[str, Any] = {"user_id": user_id, "order_id": int(order_id)}
    if address:
        payload["address"] = str(address)
    resp = requests.post(f"{base}/api/shipments/create/", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()

