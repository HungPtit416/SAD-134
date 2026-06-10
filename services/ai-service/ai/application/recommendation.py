from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from .interaction_gateway import list_events
from .product_gateway import Product, get_product, list_products
from .graph_gateway import recommend_from_graph, user_product_edge_count
from .rating_utils import (
    query_mentions_rating,
    query_wants_high_rating,
    query_wants_low_rating,
    rating_quality_score,
)
from .sequence_predictor import predict_next_action
from ..infrastructure.models import GnnProductEmbedding, GnnUserEmbedding, ProductEmbedding, UserEmbedding


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
    if any(k in q for k in ["sách", "sach", "book", "novel", "truyện", "truyen", "tác giả", "tac gia", "author", "fiction", "harry", "sapiens", "đắc nhân", "dac nhan"]):
        keywords = ["book", "sách", "sach", "novel", "fiction", "non-fiction", "children", "author", "harry", "sapiens", "dune", "orwell"]
    elif any(k in q for k in ["thời trang", "thoi trang", "fashion", "quần áo", "quan ao", "giày", "giay", "váy", "vay", "túi", "tui", "áo", "ao", "sneaker", "jeans", "dress", "nike", "uniqlo", "zara"]):
        keywords = ["fashion", "clothing", "shoes", "bags", "dress", "jeans", "sneaker", "tote", "uniqlo", "nike", "zara", "levi", "coach"]
    elif any(k in q for k in ["laptop", "notebook", "macbook"]):
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
        hay = f"{p.name or ''} {p.category_name or ''} {p.extra_blob or ''}".lower()
        if any(k in hay for k in keywords):
            matched.append(Recommendation(product_id=p.id, score=100.0, reason="query-match"))
        if len(matched) >= limit:
            break
    return matched


def _recommendations_from_ratings(user_id: str, query: str | None, limit: int) -> list[Recommendation]:
    q = (query or "").strip().lower()
    if not query_mentions_rating(q):
        return []

    events = list_events(user_id, limit=200)
    interacted: set[int] = {e.product_id for e in events if e.product_id is not None}

    try:
        products = list_products()
    except Exception:  # noqa: BLE001
        return []

    want_low = query_wants_low_rating(q)
    want_high = query_wants_high_rating(q) or not want_low

    pool = [p for p in products if p.id not in interacted and rating_quality_score(p) > 0]
    if not pool:
        return []

    pool.sort(key=lambda p: rating_quality_score(p), reverse=want_high)
    reason = "high-rating" if want_high else "low-rating"
    return [
        Recommendation(product_id=p.id, score=float(rating_quality_score(p)), reason=reason)
        for p in pool[:limit]
    ]


def _apply_rating_score_boost(items: list[Recommendation], limit: int) -> list[Recommendation]:
    if not items:
        return items
    try:
        prod_map = {p.id: p for p in list_products()}
    except Exception:  # noqa: BLE001
        return items[:limit]

    boosted: list[Recommendation] = []
    for r in items:
        p = prod_map.get(r.product_id)
        bonus = rating_quality_score(p) * 0.2 if p else 0.0
        boosted.append(Recommendation(product_id=r.product_id, score=float(r.score) + bonus, reason=r.reason))
    boosted.sort(key=lambda x: (-float(x.score), x.product_id))
    return boosted[:limit]


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


def _recommendations_from_event_categories(user_id: str, limit: int) -> list[Recommendation]:
    """
    Same-category picks from weighted recent events (view / cart / purchase).
    Used to prepend signal when graph or embedding recommenders ignore category.
    """

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

    if not cat_scores:
        return []

    try:
        products = list_products()
    except Exception:  # noqa: BLE001
        return []

    scored: list[Recommendation] = []
    for p in products:
        if p.id in interacted:
            continue
        score = 0.0
        reason = "popular"
        if p.category_id is not None and p.category_id in cat_scores:
            score += cat_scores[p.category_id]
            reason = "same-category"
        score += rating_quality_score(p) * 0.25
        scored.append(Recommendation(product_id=p.id, score=score, reason=reason))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:limit]


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


def _recommendations_from_gnn_embeddings(user_id: str, limit: int) -> list[Recommendation]:
    """
    Phase-4 embeddings trained from LightGCN.
    Stored separately (GnnUserEmbedding/GnnProductEmbedding) for clean evaluation.
    """

    try:
        from pgvector.django import CosineDistance
    except Exception:  # noqa: BLE001
        CosineDistance = None  # type: ignore[assignment]

    if CosineDistance is None:
        return []

    ue = GnnUserEmbedding.objects.filter(user_id=user_id).first()
    if ue is None:
        return []

    events = list_events(user_id, limit=200)
    interacted: set[int] = {e.product_id for e in events if e.product_id is not None}
    qs = (
        GnnProductEmbedding.objects.all()
        .exclude(product_id__in=list(interacted))
        .order_by(CosineDistance("embedding", ue.embedding))[:limit]
    )
    rows = list(qs)
    if not rows:
        return []
    return [
        Recommendation(product_id=int(r.product_id), score=float(1.0 / (1e-6 + i + 1)), reason="gnn-embedding")
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
    Same-category picks from recent views/carts/purchases are prepended whenever graph or embeddings
    are blended so short accessory-heavy sessions are not drowned out by global embedding neighbors.
    """

    limit = max(1, min(50, int(limit)))
    min_edges = max(0, int(getattr(settings, "GRAPH_MIN_PRODUCT_EDGES_FOR_BLEND", 2)))

    q_recs = _recommendations_from_query(user_id, query, limit=limit)
    rating_recs = _recommendations_from_ratings(user_id, query, limit=limit)
    seed_recs = _recommendations_from_seed_products(user_id, seed_product_ids, limit=limit)
    graph = recommend_from_graph(user_id, limit=limit, seed_product_ids=seed_product_ids or None)
    emb = _recommendations_from_embeddings(user_id, limit=limit)
    gnn = _recommendations_from_gnn_embeddings(user_id, limit=limit)

    pred = predict_next_action(user_id, seq_len=6)
    seed_pref = bool(seed_product_ids)
    behavior_cat_recs = _recommendations_from_event_categories(user_id, limit)

    # If phase-4 GNN embeddings exist, prefer them as the strongest learned signal.
    # Then blend graph and baseline embeddings for robustness.
    if gnn:
        items = _rerank_by_next_action(gnn, pred.action, limit)
        # Fill with graph/embeddings if needed.
        items = _dedupe_recommendations(items + graph + emb, limit)
        if seed_pref:
            items = _dedupe_recommendations(q_recs + behavior_cat_recs + items, limit)
            if len(items) < limit:
                items = _dedupe_recommendations(items + seed_recs, limit)
        else:
            items = _dedupe_recommendations(q_recs + seed_recs + behavior_cat_recs + items, limit)
        return _finalize_recommendations(_rerank_by_query(items, query, limit), query, limit, rating_recs)

    if graph and emb:
        has_cooc = any(g.reason == "graph-cooccurrence" for g in graph)
        if has_cooc:
            items = [Recommendation(product_id=g.product_id, score=g.score, reason=g.reason) for g in graph]
            items = _rerank_by_next_action(items, pred.action, limit)
            if seed_pref:
                items = _dedupe_recommendations(q_recs + behavior_cat_recs + items, limit)
                if len(items) < limit:
                    items = _dedupe_recommendations(items + seed_recs, limit)
            else:
                items = _dedupe_recommendations(q_recs + seed_recs + behavior_cat_recs + items, limit)
            return _finalize_recommendations(_rerank_by_query(items, query, limit), query, limit, rating_recs)

        edges = user_product_edge_count(user_id)
        if edges >= min_edges:
            graph_recs = [Recommendation(product_id=g.product_id, score=g.score, reason=g.reason) for g in graph]
            items = _dedupe_recommendations(emb + graph_recs, limit)
            items = _rerank_by_next_action(items, pred.action, limit)
            items = _dedupe_recommendations(q_recs + seed_recs + behavior_cat_recs + items, limit)
            return _finalize_recommendations(_rerank_by_query(items, query, limit), query, limit, rating_recs)

        items = _rerank_by_next_action(emb, pred.action, limit)
        items = _dedupe_recommendations(q_recs + seed_recs + behavior_cat_recs + items, limit)
        return _finalize_recommendations(_rerank_by_query(items, query, limit), query, limit, rating_recs)

    if graph:
        items = [Recommendation(product_id=g.product_id, score=g.score, reason=g.reason) for g in graph]
        items = _rerank_by_next_action(items, pred.action, limit)
        if seed_pref:
            items = _dedupe_recommendations(q_recs + behavior_cat_recs + items, limit)
            if len(items) < limit:
                items = _dedupe_recommendations(items + seed_recs, limit)
        else:
            items = _dedupe_recommendations(q_recs + seed_recs + behavior_cat_recs + items, limit)
        return _finalize_recommendations(_rerank_by_query(items, query, limit), query, limit, rating_recs)

    if emb:
        items = _rerank_by_next_action(emb, pred.action, limit)
        if seed_pref:
            items = _dedupe_recommendations(q_recs + behavior_cat_recs + items, limit)
            if len(items) < limit:
                items = _dedupe_recommendations(items + seed_recs, limit)
        else:
            items = _dedupe_recommendations(q_recs + seed_recs + behavior_cat_recs + items, limit)
        return _finalize_recommendations(_rerank_by_query(items, query, limit), query, limit, rating_recs)

    events = list_events(user_id, limit=200)
    # If the user has no behavior yet (cold start) and the UI didn't provide query/seeds,
    # return empty to avoid showing "random popular" items.
    meaningful = [e for e in events if (e.product_id is not None) or (e.query or "").strip()]
    if not meaningful and not (query or "").strip() and not seed_product_ids:
        if rating_recs:
            return _finalize_recommendations(rating_recs, query, limit, [])
        return []
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
        score += rating_quality_score(p) * 0.25
        scored.append(Recommendation(product_id=p.id, score=score, reason=reason))

    scored.sort(key=lambda x: x.score, reverse=True)
    items = _rerank_by_next_action(scored[:limit], pred.action, limit)
    if seed_pref:
        items = _dedupe_recommendations(q_recs + items, limit)
        if len(items) < limit:
            items = _dedupe_recommendations(items + seed_recs, limit)
    else:
        items = _dedupe_recommendations(q_recs + seed_recs + items, limit)
    return _finalize_recommendations(_rerank_by_query(items, query, limit), query, limit, rating_recs)


def _finalize_recommendations(
    items: list[Recommendation],
    query: str | None,
    limit: int,
    rating_recs: list[Recommendation],
) -> list[Recommendation]:
    if rating_recs:
        items = _dedupe_recommendations(rating_recs + items, limit)
    items = _apply_rating_score_boost(items, limit)
    q = (query or "").strip().lower()
    if query_mentions_rating(q):
        items = sorted(
            items,
            key=lambda r: (
                0 if r.reason in {"high-rating", "low-rating"} else 1,
                -float(r.score),
                r.product_id,
            ),
        )
    return items[:limit]


def _rerank_by_query(items: list[Recommendation], query: str | None, limit: int) -> list[Recommendation]:
    """
    If the UI provides a search query (e.g. "laptop"), boost items whose product name/category matches it.
    This helps when the user hasn't clicked a product yet (so graph/embeddings have weak signals).
    """

    q = (query or "").strip().lower()
    if not items or not q:
        return items[:limit]

    # Keep explicit query/rating intent first.
    if any(r.reason in {"query-match", "high-rating", "low-rating"} for r in items):
        pri = {"query-match": 0, "high-rating": 1, "low-rating": 1}
        out = sorted(items, key=lambda r: (pri.get(r.reason, 2), -float(r.score)))
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
            "high-rating": 0,
            "low-rating": 0,
            "graph-cooccurrence": 1,
            "behavior-embedding": 2,
            "gnn-embedding": 2,
            "graph-same-category": 3,
            "same-category": 4,
            "seed-category": 4,
            "popular": 5,
        }
    else:
        # discovery intent
        reason_pri = {
            "high-rating": 0,
            "behavior-embedding": 1,
            "gnn-embedding": 1,
            "graph-same-category": 2,
            "same-category": 3,
            "seed-category": 3,
            "graph-cooccurrence": 4,
            "low-rating": 4,
            "popular": 5,
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
                "image": p.image,
                "ratings": p.ratings,
                "no_of_ratings": p.no_of_ratings,
                "main_category": p.main_category,
                "category": {"id": p.category_id, "name": p.category_name} if p.category_id or p.category_name else None,
                "book": (
                    {
                        "author": p.book.author,
                        "publisher": p.book.publisher,
                        "isbn": p.book.isbn,
                        "language": p.book.language,
                    }
                    if p.book
                    else None
                ),
                "electronics": (
                    {
                        "brand": p.electronics.brand,
                        "color": p.electronics.color,
                        "warranty_months": p.electronics.warranty_months,
                    }
                    if p.electronics
                    else None
                ),
                "fashion": (
                    {
                        "brand": p.fashion.brand,
                        "size": p.fashion.size,
                        "color": p.fashion.color,
                        "gender": p.fashion.gender,
                    }
                    if p.fashion
                    else None
                ),
                "rank": id_to_rank[p.id] + 1,
            }
        )
    rows.sort(key=lambda r: r["rank"])
    return rows
