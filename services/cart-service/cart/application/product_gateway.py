import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class ProductSnapshot:
    id: int
    price: str | None
    currency: str | None


def fetch_product_snapshot(product_id: int) -> ProductSnapshot:
    base = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:8001").rstrip("/")
    url = f"{base}/api/products/{product_id}/"
    resp = requests.get(url, timeout=5)
    if resp.status_code != 200:
        return ProductSnapshot(id=product_id, price=None, currency=None)
    data: dict[str, Any] = resp.json()
    return ProductSnapshot(id=int(data["id"]), price=str(data.get("price")), currency=str(data.get("currency")))

