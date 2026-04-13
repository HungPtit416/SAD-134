import os
from typing import Any

import requests


def fetch_cart(user_id: str) -> dict[str, Any]:
    base = os.environ.get("CART_SERVICE_URL", "http://localhost:8002").rstrip("/")
    resp = requests.get(f"{base}/api/cart/", params={"user_id": user_id}, timeout=5)
    resp.raise_for_status()
    return resp.json()


def clear_cart(user_id: str) -> None:
    base = os.environ.get("CART_SERVICE_URL", "http://localhost:8002").rstrip("/")
    requests.delete(f"{base}/api/cart/clear/", params={"user_id": user_id, "release": "0"}, timeout=5)

