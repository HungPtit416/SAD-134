from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


@dataclass(frozen=True)
class InteractionEvent:
    id: int
    user_id: str
    event_type: str
    product_id: int | None
    query: str | None
    metadata: dict[str, Any]
    created_at: str


def list_events(user_id: str, limit: int = 100) -> list[InteractionEvent]:
    url = f"{settings.INTERACTION_SERVICE_URL}/api/events/list/"
    resp = requests.get(url, params={"user_id": user_id, "limit": min(max(limit, 1), 500)}, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    out: list[InteractionEvent] = []
    for row in (data or []):
        out.append(
            InteractionEvent(
                id=int(row["id"]),
                user_id=str(row["user_id"]),
                event_type=str(row["event_type"]),
                product_id=(int(row["product_id"]) if row.get("product_id") is not None else None),
                query=(row.get("query") or None),
                metadata=(row.get("metadata") or {}),
                created_at=str(row.get("created_at") or ""),
            )
        )
    return out


def list_recent_events(limit: int = 5000) -> list[InteractionEvent]:
    url = f"{settings.INTERACTION_SERVICE_URL}/api/events/list/"
    resp = requests.get(url, params={"limit": min(max(limit, 1), 5000)}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    out: list[InteractionEvent] = []
    for row in (data or []):
        out.append(
            InteractionEvent(
                id=int(row["id"]),
                user_id=str(row["user_id"]),
                event_type=str(row["event_type"]),
                product_id=(int(row["product_id"]) if row.get("product_id") is not None else None),
                query=(row.get("query") or None),
                metadata=(row.get("metadata") or {}),
                created_at=str(row.get("created_at") or ""),
            )
        )
    return out

