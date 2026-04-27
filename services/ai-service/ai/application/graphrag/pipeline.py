from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from django.conf import settings

from .seed import pick_seeds
from .traverse import traverse_subgraph
from .rerank import rerank_subgraph
from .compile_context import compile_evidence
from .types import GraphRagContext, GraphEvidence


def build_graphrag_context(
    *,
    user_id: str,
    message: str,
    evidence_limit: int = 20,
) -> GraphRagContext:
    """
    GraphRAG pipeline:
      seeds -> traverse -> rerank -> compile evidence
    """

    seeds = pick_seeds(user_id, message)
    # Pass explicit product seeds (from chat message) so SIMILAR evidence is visible even when
    # the user's historical events don't overlap the catalog IDs.
    sub = traverse_subgraph(user_id=user_id, seed_product_ids=(seeds.mentioned_product_ids or seeds.recent_product_ids))
    if not sub.get("enabled"):
        return GraphRagContext(enabled=False, seed=asdict(seeds), stats={"note": "neo4j disabled"}, evidence=[])

    sub = rerank_subgraph(sub, evidence_limit=evidence_limit)
    evidence = compile_evidence(user_id=user_id, subgraph=sub, message=message, evidence_limit=evidence_limit)

    stats = {
        "searched_queries": len(sub.get("searched_queries") or []),
        "co_user_recs": len(sub.get("co_user_recs") or []),
        "user_categories": len(sub.get("user_categories") or []),
        "evidence_count": len(evidence),
        "evidence_limit": int(evidence_limit),
    }
    return GraphRagContext(enabled=True, seed=asdict(seeds), stats=stats, evidence=evidence)


def export_graphrag_example(
    *,
    user_id: str,
    message: str,
    out_path: str,
    evidence_limit: int = 20,
) -> dict[str, Any]:
    """
    Export a single JSON file for the final report: the exact evidence your GraphRAG produced.
    """

    ctx = build_graphrag_context(user_id=user_id, message=message, evidence_limit=evidence_limit)

    def ev_to_dict(ev: GraphEvidence) -> dict[str, Any]:
        d = asdict(ev)
        # Ensure JSON-friendly floats/ints.
        d["score"] = float(d.get("score") or 0.0)
        if d.get("product_id") is not None:
            d["product_id"] = int(d["product_id"])
        return d

    payload = {
        "user_id": user_id,
        "message": (message or "")[:500],
        "enabled": bool(ctx.enabled),
        "seed": ctx.seed,
        "stats": ctx.stats,
        "evidence": [ev_to_dict(e) for e in ctx.evidence],
        "neo4j_uri_configured": bool(getattr(settings, "NEO4J_URI", "")),
    }

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"written": str(path), "evidence_count": len(payload["evidence"])}

