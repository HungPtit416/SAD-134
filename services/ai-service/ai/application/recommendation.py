from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from .interaction_gateway import list_events
from .product_gateway import Product, get_product, list_products
from .graph_gateway import recommend_from_graph, user_product_edge_count
from ..infrastructure.models import ProductEmbedding, UserEmbedding


@dataclass(frozen=True)
class Recommendation:
    product_id: int
    score: float
    reason: str


def _dedupe_recommendations(items: list[Recommendation], limit: int) -> list[Recommendation]:
    seen: set[int] = set()
    out: list[Recommendation] = []
    for r in items:
        if r.product_id in seen:
            continue
        seen.add(r.product_id)
        out.append(r)
        if len(out) >= limit:
            break
    return out


def _recommendations_from_embeddings(user_id: str, limit: int) -> list[Recommendation]:
    try:
        from pgvector.django import CosineDistance
    except Exception:  # noqa: BLE001
        CosineDistance = None  # type: ignore[assignment]

    if CosineDistance is None:
        return []

    ue = UserEmbedding.objects.filter(user_id=user_id).first()
    if ue is None:
        return []

    events = list_events(user_id, limit=200)
    interacted: set[int] = {e.product_id for e in events if e.product_id is not None}
    qs = (
        ProductEmbedding.objects.all()
        .exclude(product_id__in=list(interacted))
        .order_by(CosineDistance("embedding", ue.embedding))[:limit]
    )
    rows = list(qs)
    if not rows:
        return []
    return [
        Recommendation(product_id=int(r.product_id), score=float(1.0 / (1e-6 + i + 1)), reason="behavior-embedding")
        for i, r in enumerate(rows)
    ]


def recommend_products(user_id: str, limit: int = 10) -> list[Recommendation]:
    """
    When Neo4j + behavior embeddings both exist:
    - Strong graph: at least one co-occurrence hit → prefer graph.
    - Weak graph (only same-category expansion) → prefer embeddings first, then fill from graph.
    When only one source exists, use it; else category heuristics from recent events.
    """

    limit = max(1, min(50, int(limit)))
    min_edges = max(0, int(getattr(settings, "GRAPH_MIN_PRODUCT_EDGES_FOR_BLEND", 2)))

    graph = recommend_from_graph(user_id, limit=limit)
    emb = _recommendations_from_embeddings(user_id, limit=limit)

    if graph and emb:
        has_cooc = any(g.reason == "graph-cooccurrence" for g in graph)
        if has_cooc:
            return [Recommendation(product_id=g.product_id, score=g.score, reason=g.reason) for g in graph]

        edges = user_product_edge_count(user_id)
        if edges >= min_edges:
            graph_recs = [Recommendation(product_id=g.product_id, score=g.score, reason=g.reason) for g in graph]
            return _dedupe_recommendations(emb + graph_recs, limit)

        return emb

    if graph:
        return [Recommendation(product_id=g.product_id, score=g.score, reason=g.reason) for g in graph]

    if emb:
        return emb

    events = list_events(user_id, limit=200)
    interacted: set[int] = {e.product_id for e in events if e.product_id is not None}

    cat_scores: dict[int, float] = {}
    for e in events:
        if e.product_id is None:
            continue
        try:
            p = get_product(int(e.product_id))
        except Exception:  # noqa: BLE001
            continue
        if p.category_id is None:
            continue
        w = 1.0
        if e.event_type == "add_to_cart":
            w = 3.0
        elif e.event_type == "purchase":
            w = 5.0
        cat_scores[p.category_id] = cat_scores.get(p.category_id, 0.0) + w

    products = list_products()
    scored: list[Recommendation] = []
    for p in products:
        if p.id in interacted:
            continue
        score = 0.0
        reason = "popular"
        if p.category_id is not None and p.category_id in cat_scores:
            score += cat_scores[p.category_id]
            reason = "same-category"
        scored.append(Recommendation(product_id=p.id, score=score, reason=reason))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:limit]


def hydrate_products(recs: list[Recommendation]) -> list[dict]:
    """
    Convert recommendation IDs to product objects for the API response.
    """

    id_to_rank = {r.product_id: i for i, r in enumerate(recs)}
    products = list_products()
    rows: list[dict] = []
    for p in products:
        if p.id not in id_to_rank:
            continue
        rows.append(
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "currency": p.currency,
                "category": {"id": p.category_id, "name": p.category_name} if p.category_id or p.category_name else None,
                "rank": id_to_rank[p.id] + 1,
            }
        )
    rows.sort(key=lambda r: r["rank"])
    return rows
