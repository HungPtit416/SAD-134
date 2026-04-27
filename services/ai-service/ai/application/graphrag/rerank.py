from __future__ import annotations

from typing import Any


def score_co_user_rec(row: dict[str, Any]) -> float:
    """
    Minimal but explicit scoring:
    - start from relationship weight (w)
    - small bonuses if there is a concrete other user id / seed product
    """

    try:
        w = float(row.get("w") or 0.0)
    except Exception:  # noqa: BLE001
        w = 0.0
    bonus = 0.0
    if row.get("other_id"):
        bonus += 0.2
    if row.get("seed_pid") is not None:
        bonus += 0.1
    return w + bonus


def rerank_subgraph(subgraph: dict[str, Any], *, evidence_limit: int = 20) -> dict[str, Any]:
    evidence_limit = max(1, min(60, int(evidence_limit)))
    co = list(subgraph.get("co_user_recs") or [])
    co.sort(key=score_co_user_rec, reverse=True)
    subgraph["co_user_recs"] = co[: max(0, min(len(co), evidence_limit * 2))]
    return subgraph

