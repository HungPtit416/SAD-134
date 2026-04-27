from __future__ import annotations

from typing import Any

from ..product_gateway import get_product
from .types import GraphEvidence
from .rerank import score_co_user_rec


def _safe_product_details(product_id: int) -> dict[str, Any] | None:
    try:
        p = get_product(int(product_id))
    except Exception:  # noqa: BLE001
        return None
    return {
        "product_id": int(p.id),
        "name": p.name,
        "sku": p.sku,
        "category": p.category_name,
        "price": p.price,
        "currency": p.currency,
    }


def compile_evidence(
    *,
    user_id: str,
    subgraph: dict[str, Any],
    message: str,
    evidence_limit: int = 20,
) -> list[GraphEvidence]:
    evidence_limit = max(1, min(60, int(evidence_limit)))
    out: list[GraphEvidence] = []

    # Evidence A: user's most weighted searches (grounding query intent)
    for q in (subgraph.get("searched_queries") or [])[: min(3, evidence_limit)]:
        text = str(q.get("text") or "").strip()
        if not text:
            continue
        try:
            w = float(q.get("w") or 0.0)
        except Exception:  # noqa: BLE001
            w = 0.0
        out.append(
            GraphEvidence(
                type="user->query",
                score=w,
                path=[
                    {"label": "User", "id": user_id},
                    {"label": "SEARCHED", "w": w},
                    {"label": "Query", "text": text},
                ],
                product_id=None,
                details={"query_text": text},
            )
        )
        if len(out) >= evidence_limit:
            return out

    # Evidence B: product similarity recommendations (Product)-[:SIMILAR]->(Product)
    for row in (subgraph.get("similar_recs") or []):
        rec_pid = row.get("rec_pid")
        seed_pid = row.get("seed_pid")
        if rec_pid is None or seed_pid is None:
            continue
        try:
            pid = int(rec_pid)
            seed = int(seed_pid)
        except Exception:  # noqa: BLE001
            continue
        try:
            sc = float(row.get("score") or 0.0)
        except Exception:  # noqa: BLE001
            sc = 0.0
        details = _safe_product_details(pid)
        out.append(
            GraphEvidence(
                type="product->similar-product",
                score=float(sc),
                path=[
                    {"label": "User", "id": user_id},
                    {"label": "INTERACTED", "seed_product_id": seed},
                    {"label": "SIMILAR", "score": float(sc)},
                    {"label": "Product", "id": pid},
                ],
                product_id=pid,
                details={"seed_product_id": seed, "rec": details},
            )
        )
        if len(out) >= evidence_limit:
            return out

    # Evidence C: similar-user recommendations
    co_cap = max(1, min(8, evidence_limit - len(out)))
    for row in (subgraph.get("co_user_recs") or [])[:co_cap]:
        rec_pid = row.get("rec_pid")
        if rec_pid is None:
            continue
        try:
            pid = int(rec_pid)
        except Exception:  # noqa: BLE001
            continue
        sc = score_co_user_rec(row)
        details = _safe_product_details(pid)
        out.append(
            GraphEvidence(
                type="similar-user->product",
                score=float(sc),
                path=[
                    {"label": "User", "id": user_id},
                    {"label": "CO_OCCUR_WITH_USER", "other_user_id": row.get("other_id"), "seed_product_id": row.get("seed_pid")},
                    {"label": "RECOMMENDS", "w": row.get("w")},
                    {"label": "Product", "id": pid},
                ],
                product_id=pid,
                details=details,
            )
        )
        if len(out) >= evidence_limit:
            return out

    # Evidence D: categories user touched (helps when product list is empty)
    for c in (subgraph.get("user_categories") or [])[: min(6, evidence_limit - len(out))]:
        cid = c.get("id")
        name = c.get("name")
        try:
            w = float(c.get("w") or 0.0)
        except Exception:  # noqa: BLE001
            w = 0.0
        out.append(
            GraphEvidence(
                type="user->category",
                score=w,
                path=[
                    {"label": "User", "id": user_id},
                    {"label": "TOUCHED_CATEGORY", "w": w},
                    {"label": "Category", "id": cid, "name": name},
                ],
                product_id=None,
                details={"category_id": cid, "category_name": name, "weight": w, "message_seed": (message or "")[:200]},
            )
        )
        if len(out) >= evidence_limit:
            return out

    return out

