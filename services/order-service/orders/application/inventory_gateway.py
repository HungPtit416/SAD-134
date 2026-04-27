import os
from typing import Any

import requests


class InventoryError(RuntimeError):
    pass


def _base() -> str:
    return os.environ.get("INVENTORY_SERVICE_URL", "http://localhost:8005").rstrip("/")


def reserve_stock(product_id: int, quantity: int) -> dict[str, Any]:
    resp = requests.post(
        f"{_base()}/api/stock/reserve/",
        json={"product_id": int(product_id), "quantity": int(quantity)},
        timeout=10,
    )
    if resp.status_code == 409:
        data = resp.json()
        raise InventoryError(f"Insufficient stock (available={data.get('available')})")
    resp.raise_for_status()
    return resp.json()


def release_stock(product_id: int, quantity: int) -> dict[str, Any]:
    resp = requests.post(
        f"{_base()}/api/stock/release/",
        json={"product_id": int(product_id), "quantity": int(quantity)},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

