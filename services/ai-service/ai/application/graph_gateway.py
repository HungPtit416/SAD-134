from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings

try:
    from neo4j import GraphDatabase
except Exception:  # noqa: BLE001
    GraphDatabase = None  # type: ignore[assignment]


@dataclass(frozen=True)
class GraphRecommendation:
    product_id: int
    score: float
    reason: str


def _enabled() -> bool:
    return bool(settings.NEO4J_URI) and GraphDatabase is not None


def upsert_event_to_graph(
    *,
    user_id: str,
    event_type: str,
    product_id: int | None = None,
    query: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Best-effort Graph KB update.

    Nodes:
      (:User {id})
      (:Product {id})
      (:Query {text})

    Relationships:
      (u)-[:VIEWED|CLICKED|ADDED_TO_CART|PURCHASED {w}]->(p)
      (u)-[:SEARCHED {w}]->(q)
    """

    if not _enabled():
        return

    rel = {
        "view": "VIEWED",
        "click": "CLICKED",
        "add_to_cart": "ADDED_TO_CART",
        "purchase": "PURCHASED",
        "search": "SEARCHED",
    }.get(event_type, "EVENT")

    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            session.run("MERGE (u:User {id: $user_id})", user_id=user_id)
            if product_id is not None:
                session.run("MERGE (p:Product {id: $pid})", pid=int(product_id))
                session.run(
                    f"""
                    MATCH (u:User {{id: $user_id}}), (p:Product {{id: $pid}})
                    MERGE (u)-[r:{rel}]->(p)
                    ON CREATE SET r.w = 1
                    ON MATCH SET r.w = coalesce(r.w, 0) + 1
                    """,
                    user_id=user_id,
                    pid=int(product_id),
                )
            if query:
                session.run("MERGE (q:Query {text: $q})", q=str(query))
                session.run(
                    f"""
                    MATCH (u:User {{id: $user_id}}), (q:Query {{text: $q}})
                    MERGE (u)-[r:{rel}]->(q)
                    ON CREATE SET r.w = 1
                    ON MATCH SET r.w = coalesce(r.w, 0) + 1
                    """,
                    user_id=user_id,
                    q=str(query),
                )
    finally:
        driver.close()


def recommend_from_graph(user_id: str, limit: int = 10) -> list[GraphRecommendation]:
    if not _enabled():
        return []

    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            res = session.run(
                """
                MATCH (u:User {id: $user_id})-[r]->(p:Product)
                WITH p, sum(coalesce(r.w, 1)) AS w
                ORDER BY w DESC
                RETURN p.id AS product_id, w AS score
                LIMIT $limit
                """,
                user_id=user_id,
                limit=int(limit),
            )
            out: list[GraphRecommendation] = []
            for row in res:
                out.append(
                    GraphRecommendation(
                        product_id=int(row["product_id"]),
                        score=float(row["score"]),
                        reason="graph-neighbor",
                    )
                )
            return out
    finally:
        driver.close()

