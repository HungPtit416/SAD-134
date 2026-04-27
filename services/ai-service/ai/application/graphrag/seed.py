from __future__ import annotations

import re
from dataclasses import dataclass

from ..interaction_gateway import list_events


@dataclass(frozen=True)
class GraphSeeds:
    user_id: str
    query_texts: list[str]
    recent_product_ids: list[int]
    mentioned_product_ids: list[int]


def _extract_queries_from_message(message: str) -> list[str]:
    msg = (message or "").strip()
    if not msg:
        return []
    # Keep only a couple of short query candidates; avoid prompt injection via long content.
    s = re.sub(r"\s+", " ", msg)[:200]
    return [s]

def _extract_product_ids_from_message(message: str) -> list[int]:
    s = (message or "")
    ids: list[int] = []
    for m in re.finditer(r"product_id\s*[:\s]*(\d+)", s, flags=re.I):
        ids.append(int(m.group(1)))
    for m in re.finditer(r"#\s*(\d+)\b", s):
        n = int(m.group(1))
        if n not in ids:
            ids.append(n)
    return ids[:10]


def pick_seeds(user_id: str, message: str, *, history_limit: int = 80) -> GraphSeeds:
    """
    Select a small set of seed nodes from:
    - user_id
    - chat message (as a Query seed)
    - recent interacted products (from interaction-service)
    """

    events = list_events(user_id, limit=max(10, min(500, int(history_limit))))
    # newest first in API; keep first few product signals
    prod: list[int] = []
    for e in events:
        if e.product_id is None:
            continue
        if e.event_type not in {"view", "click", "add_to_cart", "purchase"}:
            continue
        pid = int(e.product_id)
        if pid not in prod:
            prod.append(pid)
        if len(prod) >= 8:
            break

    q = _extract_queries_from_message(message)
    mentioned = _extract_product_ids_from_message(message)
    return GraphSeeds(user_id=user_id, query_texts=q, recent_product_ids=prod, mentioned_product_ids=mentioned)

