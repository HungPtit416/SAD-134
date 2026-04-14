from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


@dataclass(frozen=True)
class Product:
    id: int
    sku: str | None
    name: str
    description: str | None
    price: str | None
    currency: str | None
    category_id: int | None
    category_name: str | None


def list_products() -> list[Product]:
    url = f"{settings.PRODUCT_SERVICE_URL}/api/products/"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    rows = data if isinstance(data, list) else data.get("results") or []
    out: list[Product] = []
    for r in rows:
        cat = r.get("category") or {}
        out.append(
            Product(
                id=int(r["id"]),
                sku=r.get("sku"),
                name=str(r.get("name") or ""),
                description=r.get("description"),
                price=str(r.get("price")) if r.get("price") is not None else None,
                currency=r.get("currency"),
                category_id=(int(cat["id"]) if cat and cat.get("id") is not None else None),
                category_name=(str(cat.get("name")) if cat else None),
            )
        )
    return out


def get_product(product_id: int) -> Product:
    url = f"{settings.PRODUCT_SERVICE_URL}/api/products/{product_id}/"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    r: dict[str, Any] = resp.json()
    cat = r.get("category") or {}
    return Product(
        id=int(r["id"]),
        sku=r.get("sku"),
        name=str(r.get("name") or ""),
        description=r.get("description"),
        price=str(r.get("price")) if r.get("price") is not None else None,
        currency=r.get("currency"),
        category_id=(int(cat["id"]) if cat and cat.get("id") is not None else None),
        category_name=(str(cat.get("name")) if cat else None),
    )

