from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from ..infrastructure.models import DocumentChunk
from .openai_client import embed_texts
from .product_gateway import list_products


@dataclass(frozen=True)
class IndexResult:
    upserted: int


def _product_to_doc(p) -> tuple[str, str, str, dict]:
    title = p.name
    content = "\n".join(
        [
            f"Name: {p.name}",
            f"SKU: {p.sku or ''}",
            f"Category: {p.category_name or ''}",
            f"Price: {p.price or ''} {p.currency or ''}".strip(),
            "",
            (p.description or ""),
        ]
    ).strip()
    meta = {"sku": p.sku, "category": p.category_name, "currency": p.currency, "price": p.price}
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

