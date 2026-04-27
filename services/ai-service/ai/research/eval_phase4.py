from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..application.interaction_gateway import list_recent_events
from ..infrastructure.models import GnnProductEmbedding, GnnUserEmbedding, ProductEmbedding, UserEmbedding


@dataclass(frozen=True)
class UserHoldout:
    user_id: str
    heldout_product_id: int
    seen_product_ids: set[int]


def build_holdout(*, limit_events: int = 12000) -> list[UserHoldout]:
    """
    Simple offline holdout:
    - for each user, take the last product interaction as heldout
    - previous interactions are "seen"
    """

    events = list_recent_events(limit=limit_events)
    # sort by created_at asc (string ISO is OK for order in this dataset)
    events = sorted(events, key=lambda e: e.created_at)

    by_user: dict[str, list[int]] = {}
    for e in events:
        if e.product_id is None:
            continue
        if e.event_type not in {"view", "click", "add_to_cart", "purchase"}:
            continue
        by_user.setdefault(str(e.user_id), []).append(int(e.product_id))

    out: list[UserHoldout] = []
    for u, seq in by_user.items():
        if len(seq) < 3:
            continue
        held = int(seq[-1])
        seen = set(int(x) for x in seq[:-1])
        out.append(UserHoldout(user_id=u, heldout_product_id=held, seen_product_ids=seen))
    return out


def recall_at_k(recommended: list[int], target: int, k: int) -> float:
    k = max(1, int(k))
    return 1.0 if target in recommended[:k] else 0.0


def ndcg_at_k(recommended: list[int], target: int, k: int) -> float:
    k = max(1, int(k))
    top = recommended[:k]
    if target not in top:
        return 0.0
    rank = top.index(target) + 1
    # DCG for a single relevant item: 1/log2(rank+1)
    import math

    return 1.0 / math.log2(rank + 1)


def eval_recsys(*, k_list: list[int], limit_users: int = 200) -> dict[str, Any]:
    hold = build_holdout()
    hold = hold[: max(1, min(len(hold), int(limit_users)))]
    if not hold:
        return {"ok": False, "detail": "not enough holdout users"}

    # Evaluate multiple recommenders without depending on external services (product-service/neo4j/tensorflow).
    # This keeps the offline evaluation reproducible for grading.
    max_k = max(k_list)

    try:
        import numpy as np
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"numpy missing: {e}"}

    def _topk_from_embeddings(user_vec: list[float], item_rows: list[tuple[int, list[float]]], banned: set[int], k: int) -> list[int]:
        if not user_vec or not item_rows:
            return []
        u = np.asarray(user_vec, dtype=np.float32)
        un = float(np.linalg.norm(u) + 1e-9)
        scored: list[tuple[float, int]] = []
        for pid, vec in item_rows:
            if pid in banned:
                continue
            v = np.asarray(vec, dtype=np.float32)
            dn = float(np.linalg.norm(v) + 1e-9)
            sim = float(np.dot(u, v) / (un * dn))
            scored.append((sim, int(pid)))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [pid for _, pid in scored[: max(1, int(k))]]

    # Preload embeddings into memory once.
    gnn_items = [(int(r.product_id), list(r.embedding)) for r in GnnProductEmbedding.objects.all()]
    base_items = [(int(r.product_id), list(r.embedding)) for r in ProductEmbedding.objects.all()]

    def rec_gnn(user_id: str, banned: set[int]) -> list[int]:
        ue = GnnUserEmbedding.objects.filter(user_id=user_id).first()
        if ue is None:
            return []
        return _topk_from_embeddings(list(ue.embedding), gnn_items, banned, max_k)

    def rec_skipgram(user_id: str, banned: set[int]) -> list[int]:
        ue = UserEmbedding.objects.filter(user_id=user_id).first()
        if ue is None:
            return []
        return _topk_from_embeddings(list(ue.embedding), base_items, banned, max_k)

    methods = {
        "phase4_lightgcn": rec_gnn,
        "phase2_skipgram": rec_skipgram,
    }

    out: dict[str, Any] = {"ok": True, "users": len(hold), "methods": {}}
    for name in methods:
        sums = {f"recall@{k}": 0.0 for k in k_list} | {f"ndcg@{k}": 0.0 for k in k_list}
        n = 0
        missing = 0
        for h in hold:
            ids = methods[name](h.user_id, h.seen_product_ids)
            if not ids:
                missing += 1
                continue
            for k in k_list:
                sums[f"recall@{k}"] += recall_at_k(ids, h.heldout_product_id, k)
                sums[f"ndcg@{k}"] += ndcg_at_k(ids, h.heldout_product_id, k)
            n += 1
        out["methods"][name] = {
            "evaluated_users": n,
            "missing_users": missing,
            "metrics": {k: (v / max(1, n)) for k, v in sums.items()},
        }

    return out


def write_json(path: str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

