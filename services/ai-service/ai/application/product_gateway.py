from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
from django.conf import settings


@dataclass(frozen=True)
class BookInfo:
    author: str | None = None
    publisher: str | None = None
    isbn: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class ElectronicsInfo:
    brand: str | None = None
    color: str | None = None
    warranty_months: int | None = None


@dataclass(frozen=True)
class FashionInfo:
    size: str | None = None
    color: str | None = None
    gender: str | None = None
    brand: str | None = None


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
    main_category: str | None = None
    image: str | None = None
    ratings: float | None = None
    no_of_ratings: int | None = None
    book: BookInfo | None = None
    electronics: ElectronicsInfo | None = None
    fashion: FashionInfo | None = None
    extra_blob: str = field(default="")


def _parse_book(raw: dict | None) -> BookInfo | None:
    if not raw:
        return None
    return BookInfo(
        author=raw.get("author"),
        publisher=raw.get("publisher"),
        isbn=raw.get("isbn"),
        language=raw.get("language"),
    )


def _parse_electronics(raw: dict | None) -> ElectronicsInfo | None:
    if not raw:
        return None
    wm = raw.get("warranty_months")
    return ElectronicsInfo(
        brand=raw.get("brand"),
        color=raw.get("color"),
        warranty_months=int(wm) if wm is not None else None,
    )


def _parse_fashion(raw: dict | None) -> FashionInfo | None:
    if not raw:
        return None
    return FashionInfo(
        size=raw.get("size"),
        color=raw.get("color"),
        gender=raw.get("gender"),
        brand=raw.get("brand"),
    )


def _build_extra_blob(r: dict[str, Any]) -> str:
    parts = [
        str(r.get("main_category") or ""),
        str((r.get("category") or {}).get("name") or ""),
        str(r.get("name") or ""),
        str(r.get("sku") or ""),
    ]
    book = r.get("book") or {}
    if book:
        parts.extend([book.get("author") or "", book.get("publisher") or "", book.get("language") or ""])
    elec = r.get("electronics") or {}
    if elec:
        parts.extend([elec.get("brand") or "", elec.get("color") or ""])
    fashion = r.get("fashion") or {}
    if fashion:
        parts.extend([fashion.get("brand") or "", fashion.get("size") or "", fashion.get("gender") or "", fashion.get("color") or ""])
    return " ".join(p for p in parts if p).lower()


def _parse_product_row(r: dict[str, Any]) -> Product:
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
        main_category=r.get("main_category"),
        image=r.get("image"),
        ratings=float(r["ratings"]) if r.get("ratings") is not None else None,
        no_of_ratings=int(r["no_of_ratings"]) if r.get("no_of_ratings") is not None else None,
        book=_parse_book(r.get("book")),
        electronics=_parse_electronics(r.get("electronics")),
        fashion=_parse_fashion(r.get("fashion")),
        extra_blob=_build_extra_blob(r),
    )


def list_products() -> list[Product]:
    url = f"{settings.PRODUCT_SERVICE_URL}/api/products/"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    rows = data if isinstance(data, list) else data.get("results") or []
    return [_parse_product_row(r) for r in rows]


def get_product(product_id: int) -> Product:
    url = f"{settings.PRODUCT_SERVICE_URL}/api/products/{product_id}/"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return _parse_product_row(resp.json())
