from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GraphEvidence:
    """
    A small, explicit piece of evidence to ground chat responses.
    Designed for readability in the final report.
    """

    type: str  # e.g. "query->product", "user->product", "similar-user->product"
    score: float
    path: list[dict[str, Any]]  # [{"label": "User", "id": "user-0001"}, {"label": "VIEWED", ...}, ...]
    product_id: int | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class GraphRagContext:
    enabled: bool
    seed: dict[str, Any]
    stats: dict[str, Any]
    evidence: list[GraphEvidence]

