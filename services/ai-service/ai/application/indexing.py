from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from ..infrastructure.models import DocumentChunk
from .llm_client import embed_texts
from .product_gateway import list_products


@dataclass(frozen=True)
class IndexResult:
    upserted: int


def _product_to_doc(p) -> tuple[str, str, str, dict]:
    title = p.name
    lines = [
        f"Name: {p.name}",
        f"SKU: {p.sku or ''}",
        f"Main category: {p.main_category or ''}",
        f"Category: {p.category_name or ''}",
        f"Price: {p.price or ''} {p.currency or ''}".strip(),
        f"Rating: {p.ratings or 0}/5 ({p.no_of_ratings or 0} reviews)",
    ]
    if p.book:
        lines.append(f"Author: {p.book.author or ''}")
        lines.append(f"Publisher: {p.book.publisher or ''}")
        lines.append(f"Language: {p.book.language or ''}")
    if p.electronics:
        lines.append(f"Brand: {p.electronics.brand or ''}")
        lines.append(f"Color: {p.electronics.color or ''}")
    if p.fashion:
        lines.append(f"Brand: {p.fashion.brand or ''}")
        lines.append(f"Size: {p.fashion.size or ''}")
        lines.append(f"Gender: {p.fashion.gender or ''}")
    lines.extend(["", (p.description or "")])
    content = "\n".join(lines).strip()
    meta = {
        "sku": p.sku,
        "category": p.category_name,
        "main_category": p.main_category,
        "currency": p.currency,
        "price": p.price,
        "ratings": p.ratings,
        "no_of_ratings": p.no_of_ratings,
    }
    return title, content, f"{p.id}", meta


def index_products() -> IndexResult:
    products = list_products()
    docs = [_product_to_doc(p) for p in products]
    if not docs:
        return IndexResult(upserted=0)

    embeddings = embed_texts([d[1] for d in docs]).vectors

    upserted = 0
    with transaction.atomic():
        for (title, content, source_id, meta), vec in zip(docs, embeddings, strict=False):
            obj, created = DocumentChunk.objects.update_or_create(
                source_type="product",
                source_id=source_id,
                defaults={
                    "title": title,
                    "content": content,
                    "metadata": meta,
                    "embedding": vec,
                },
            )
            upserted += 1 if created else 1
    return IndexResult(upserted=upserted)


def retrieve_similar(*, query: str, limit: int = 6) -> list[DocumentChunk]:
    """
    Vector retrieval using pgvector's cosine distance if available.
    """

    q = (query or "").strip()
    if not q:
        return []
    vec = embed_texts([q]).vectors[0]

    try:
        from pgvector.django import CosineDistance
    except Exception:  # noqa: BLE001
        CosineDistance = None  # type: ignore[assignment]

    qs = DocumentChunk.objects.all()
    if CosineDistance is None:
        # Fallback: no distance function available (should not happen if pgvector installed)
        return list(qs[: max(1, min(20, int(limit)))])

    return list(qs.order_by(CosineDistance("embedding", vec))[: max(1, min(20, int(limit)))])

