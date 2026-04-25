from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from .interaction_gateway import list_events
from .product_gateway import Product, get_product, list_products
from .graph_gateway import recommend_from_graph, user_product_edge_count
from .sequence_predictor import predict_next_action
from ..infrastructure.models import ProductEmbedding, UserEmbedding


@dataclass(frozen=True)
class Recommendation:
    product_id: int
    score: float
    reason: str


def _recommendations_from_query(user_id: str, query: str | None, limit: int) -> list[Recommendation]:
    q = (query or "").strip().lower()
    if not q:
        return []

    # Avoid recommending items the user already interacted with.
    events = list_events(user_id, limit=200)
    interacted: set[int] = {e.product_id for e in events if e.product_id is not None}

    # Lightweight Vietnamese/English keyword normalization.
    if any(k in q for k in ["laptop", "notebook", "macbook"]):
        keywords = ["laptop", "macbook", "notebook"]
    elif any(k in q for k in ["tai nghe", "headphone", "earbuds"]):
        keywords = ["tai nghe", "headphone", "earbud", "earbuds", "airpods"]
    elif any(k in q for k in ["iphone", "điện thoại", "dien thoai", "phone"]):
        keywords = ["iphone", "phone", "điện thoại", "dien thoai"]
    elif any(k in q for k in ["ipad", "tablet", "máy tính bảng", "may tinh bang"]):
        keywords = ["ipad", "tablet", "máy tính bảng", "may tinh bang"]
    else:
        toks = [t for t in q.replace(",", " ").split() if len(t) >= 3]
        keywords = toks[:2]

    try:
        products = list_products()
    except Exception:  # noqa: BLE001
        return []

    matched: list[Recommendation] = []
    for p in products:
        if p.id in interacted:
            continue
        hay = f"{p.name or ''} {p.category_name or ''}".lower()
        if any(k in hay for k in keywords):
            matched.append(Recommendation(product_id=p.id, score=100.0, reason="query-match"))
        if len(matched) >= limit:
            break
    return matched


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


def _recommendations_from_seed_products(user_id: str, seed_product_ids: list[int] | None, limit: int) -> list[Recommendation]:
    if not seed_product_ids:
        return []

    seed_set = {int(x) for x in seed_product_ids if x is not None}
    if not seed_set:
        return []

    # Avoid recommending items the user already interacted with.
    events = list_events(user_id, limit=200)
    interacted: set[int] = {e.product_id for e in events if e.product_id is not None}

    try:
        products = list_products()
    except Exception:  # noqa: BLE001
        return []

    # Determine dominant categories from seed products.
    by_id = {p.id: p for p in products}
    cat_count: dict[int, int] = {}
    for pid in seed_set:
        p = by_id.get(pid)
        if p is None or p.category_id is None:
            continue
        cat_count[int(p.category_id)] = cat_count.get(int(p.category_id), 0) + 1

    if not cat_count:
        return []

    top_cats = [cid for cid, _ in sorted(cat_count.items(), key=lambda kv: kv[1], reverse=True)[:2]]

    out: list[Recommendation] = []
    for p in products:
        if p.id in seed_set or p.id in interacted:
            continue
        if p.category_id is not None and int(p.category_id) in top_cats:
            out.append(Recommendation(product_id=p.id, score=80.0, reason="seed-category"))
        if len(out) >= limit:
            break
    return out


def recommend_products(
    user_id: str, limit: int = 10, query: str | None = None, seed_product_ids: list[int] | None = None
) -> list[Recommendation]:
    """
    When Neo4j + behavior embeddings both exist:
    - Strong graph: at least one co-occurrence hit → prefer graph.
    - Weak graph (only same-category expansion) → prefer embeddings first, then fill from graph.
    When only one source exists, use it; else category heuristics from recent events.
    """

    limit = max(1, min(50, int(limit)))
    min_edges = max(0, int(getattr(settings, "GRAPH_MIN_PRODUCT_EDGES_FOR_BLEND", 2)))

    q_recs = _recommendations_from_query(user_id, query, limit=limit)
    seed_recs = _recommendations_from_seed_products(user_id, seed_product_ids, limit=limit)
    graph = recommend_from_graph(user_id, limit=limit)
    emb = _recommendations_from_embeddings(user_id, limit=limit)

    pred = predict_next_action(user_id, seq_len=6)

    if graph and emb:
        has_cooc = any(g.reason == "graph-cooccurrence" for g in graph)
        if has_cooc:
            items = [Recommendation(product_id=g.product_id, score=g.score, reason=g.reason) for g in graph]
            items = _rerank_by_next_action(items, pred.action, limit)
            items = _dedupe_recommendations(q_recs + seed_recs + items, limit)
            return _rerank_by_query(items, query, limit)

        edges = user_product_edge_count(user_id)
        if edges >= min_edges:
            graph_recs = [Recommendation(product_id=g.product_id, score=g.score, reason=g.reason) for g in graph]
            items = _dedupe_recommendations(emb + graph_recs, limit)
            items = _rerank_by_next_action(items, pred.action, limit)
            items = _dedupe_recommendations(q_recs + seed_recs + items, limit)
            return _rerank_by_query(items, query, limit)

        items = _rerank_by_next_action(emb, pred.action, limit)
        items = _dedupe_recommendations(q_recs + seed_recs + items, limit)
        return _rerank_by_query(items, query, limit)

    if graph:
        items = [Recommendation(product_id=g.product_id, score=g.score, reason=g.reason) for g in graph]
        items = _rerank_by_next_action(items, pred.action, limit)
        items = _dedupe_recommendations(q_recs + seed_recs + items, limit)
        return _rerank_by_query(items, query, limit)

    if emb:
        items = _rerank_by_next_action(emb, pred.action, limit)
        items = _dedupe_recommendations(q_recs + seed_recs + items, limit)
        return _rerank_by_query(items, query, limit)

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
    items = _rerank_by_next_action(scored[:limit], pred.action, limit)
    items = _dedupe_recommendations(q_recs + seed_recs + items, limit)
    return _rerank_by_query(items, query, limit)


def _rerank_by_query(items: list[Recommendation], query: str | None, limit: int) -> list[Recommendation]:
    """
    If the UI provides a search query (e.g. "laptop"), boost items whose product name/category matches it.
    This helps when the user hasn't clicked a product yet (so graph/embeddings have weak signals).
    """

    q = (query or "").strip().lower()
    if not items or not q:
        return items[:limit]

    # Keep "query-match" items first.
    if any(r.reason == "query-match" for r in items):
        out = sorted(items, key=lambda r: (0 if r.reason == "query-match" else 1))
        return out[:limit]

    try:
        prod_map = {p.id: p for p in list_products()}
    except Exception:  # noqa: BLE001
        return items[:limit]

    def is_match(pid: int) -> bool:
        p = prod_map.get(pid)
        if p is None:
            return False
        hay = f"{p.name or ''} {p.category_name or ''}".lower()
        # If it reached here, just do a loose containment check.
        return q in hay

    # Stable sort: matches first, then keep existing order.
    out = sorted(items, key=lambda r: (0 if is_match(r.product_id) else 1))
    return out[:limit]


def _rerank_by_next_action(items: list[Recommendation], next_action: str | None, limit: int) -> list[Recommendation]:
    """
    Lightweight integration of the LSTM next-action predictor:
    - If predicted purchase/checkout: prioritize stronger intent signals (graph-cooccurrence, add_to_cart-like embedding).
    - If predicted browse/search: prioritize discovery signals.
    """

    if not items or not next_action:
        return items[:limit]

    # Primary: intent-based priority by "reason" buckets.
    if next_action in {"purchase", "checkout", "add_to_cart"}:
        reason_pri = {
            "graph-cooccurrence": 0,
            "behavior-embedding": 1,
            "graph-same-category": 2,
            "same-category": 3,
            "popular": 4,
        }
    else:
        # discovery intent
        reason_pri = {
            "behavior-embedding": 0,
            "graph-same-category": 1,
            "same-category": 2,
            "graph-cooccurrence": 3,
            "popular": 4,
        }

    def key(r: Recommendation):
        return (reason_pri.get(r.reason, 9), -float(r.score))

    out = sorted(items, key=key)
    return out[:limit]


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
