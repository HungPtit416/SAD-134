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


# Behavioral weights (relative importance of interaction types on user–product edges).
_PRODUCT_EDGE_WEIGHT: dict[str, float] = {
    "view": 1.0,
    "click": 2.0,
    "add_to_cart": 5.0,
    "purchase": 10.0,
}

_QUERY_EDGE_WEIGHT: dict[str, float] = {
    "search": 1.0,
}


def _enabled() -> bool:
    return bool(settings.NEO4J_URI) and GraphDatabase is not None


def _product_rel_name(event_type: str) -> str | None:
    return {
        "view": "VIEWED",
        "click": "CLICKED",
        "add_to_cart": "ADDED_TO_CART",
        "purchase": "PURCHASED",
    }.get(event_type)


def _delta_for_product(event_type: str) -> float | None:
    rel = _product_rel_name(event_type)
    if rel is None:
        return None
    return float(_PRODUCT_EDGE_WEIGHT.get(event_type, 1.0))


def _delta_for_query(event_type: str) -> float | None:
    if event_type not in _QUERY_EDGE_WEIGHT:
        return None
    return float(_QUERY_EDGE_WEIGHT[event_type])


def upsert_event_to_graph(
    *,
    user_id: str,
    event_type: str,
    product_id: int | None = None,
    query: str | None = None,
    metadata: dict[str, Any] | None = None,
    category_id: int | None = None,
    category_name: str | None = None,
) -> None:
    """
    Best-effort Graph KB update.

    Nodes:
      (:User {id})
      (:Product {id})
      (:Category {id, name})
      (:Query {text})

    Relationships:
      (u)-[:VIEWED|CLICKED|ADDED_TO_CART|PURCHASED {w}]->(p)
      (p)-[:IN_CATEGORY]->(c)
      (u)-[:SEARCHED {w}]->(q)
    """

    if not _enabled():
        return

    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            session.run("MERGE (u:User {id: $user_id})", user_id=user_id)

            if product_id is not None:
                delta = _delta_for_product(event_type)
                if delta is not None:
                    pid = int(product_id)
                    session.run("MERGE (p:Product {id: $pid})", pid=pid)
                    if category_id is not None:
                        session.run(
                            """
                            MERGE (c:Category {id: $cid})
                            ON CREATE SET c.name = $cname
                            ON MATCH SET c.name = coalesce($cname, c.name)
                            WITH c
                            MATCH (p:Product {id: $pid})
                            MERGE (p)-[:IN_CATEGORY]->(c)
                            """,
                            cid=int(category_id),
                            cname=(category_name or "")[:255],
                            pid=pid,
                        )
                    rel = _product_rel_name(event_type)
                    assert rel is not None
                    session.run(
                        f"""
                        MATCH (u:User {{id: $user_id}}), (p:Product {{id: $pid}})
                        MERGE (u)-[r:{rel}]->(p)
                        ON CREATE SET r.w = $delta
                        ON MATCH SET r.w = coalesce(r.w, 0) + $delta
                        """,
                        user_id=user_id,
                        pid=pid,
                        delta=float(delta),
                    )

            if query and (q := str(query).strip()):
                qdelta = _delta_for_query(event_type)
                if qdelta is not None:
                    session.run("MERGE (q:Query {text: $q})", q=q)
                    session.run(
                        """
                        MATCH (u:User {id: $user_id}), (q:Query {text: $q})
                        MERGE (u)-[r:SEARCHED]->(q)
                        ON CREATE SET r.w = $delta
                        ON MATCH SET r.w = coalesce(r.w, 0) + $delta
                        """,
                        user_id=user_id,
                        q=q,
                        delta=float(qdelta),
                    )
    finally:
        driver.close()


def backfill_product_categories_to_graph(
    products: list[tuple[int, int | None, str | None]],
) -> None:
    """
    MERGE Product and Category nodes and IN_CATEGORY edges from catalog tuples:
    (product_id, category_id, category_name).
    """

    if not _enabled() or not products:
        return

    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            for pid, cid, cname in products:
                session.run("MERGE (p:Product {id: $pid})", pid=int(pid))
                if cid is None:
                    continue
                session.run(
                    """
                    MERGE (c:Category {id: $cid})
                    ON CREATE SET c.name = $cname
                    ON MATCH SET c.name = coalesce($cname, c.name)
                    WITH c
                    MATCH (p:Product {id: $pid})
                    MERGE (p)-[:IN_CATEGORY]->(c)
                    """,
                    cid=int(cid),
                    cname=(cname or "")[:255],
                    pid=int(pid),
                )
    finally:
        driver.close()


def recommend_from_graph(user_id: str, limit: int = 10) -> list[GraphRecommendation]:
    """
    Recommend products using co-occurrence (users who interacted with the same items)
    and same-category expansion, excluding products the user already has an edge to.
    """

    if not _enabled():
        return []

    limit = max(1, min(50, int(limit)))
    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            seen: set[int] = set()
            out: list[GraphRecommendation] = []

            res_co = session.run(
                """
                MATCH (me:User {id: $user_id})-[r1]->(p:Product)<-[r2]-(other:User)
                WHERE me <> other
                MATCH (other)-[r3]->(rec:Product)
                WHERE NOT (me)-[]->(rec)
                WITH rec, sum(coalesce(r3.w, 1.0)) AS score
                RETURN rec.id AS product_id, score
                ORDER BY score DESC
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit,
            )
            for row in res_co:
                pid = int(row["product_id"])
                if pid in seen:
                    continue
                seen.add(pid)
                out.append(
                    GraphRecommendation(
                        product_id=pid,
                        score=float(row["score"]),
                        reason="graph-cooccurrence",
                    )
                )

            if len(out) >= limit:
                return out[:limit]

            remaining = limit - len(out)
            res_cat = session.run(
                """
                MATCH (me:User {id: $user_id})-[r]->(p:Product)-[:IN_CATEGORY]->(c:Category)
                WITH collect(DISTINCT p.id) AS my_ids, collect(DISTINCT c.id) AS cat_ids
                WHERE size(cat_ids) > 0
                MATCH (rec:Product)-[:IN_CATEGORY]->(c:Category)
                WHERE c.id IN cat_ids AND NOT rec.id IN my_ids
                RETURN rec.id AS product_id, count(*) AS score
                ORDER BY score DESC
                LIMIT $limit
                """,
                user_id=user_id,
                limit=remaining + len(seen) + 10,
            )
            for row in res_cat:
                if len(out) >= limit:
                    break
                pid = int(row["product_id"])
                if pid in seen:
                    continue
                seen.add(pid)
                out.append(
                    GraphRecommendation(
                        product_id=pid,
                        score=float(row["score"]),
                        reason="graph-same-category",
                    )
                )

            return out[:limit]
    finally:
        driver.close()


def user_product_edge_count(user_id: str) -> int:
    """How many user→product relationships exist in the graph (signal strength)."""

    if not _enabled():
        return 0

    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            row = session.run(
                """
                MATCH (u:User {id: $user_id})-[r]->(p:Product)
                RETURN count(r) AS c
                """,
                user_id=user_id,
            ).single()
            return int(row["c"]) if row else 0
    finally:
        driver.close()


def graph_context_for_rag(user_id: str, *, limit: int = 8) -> dict[str, Any]:
    """
    Graph-derived snippets for chat grounding (GraphRAG-lite): recent searches, co-occurrence picks,
    and categories the user has touched.
    """

    empty: dict[str, Any] = {
        "enabled": False,
        "searched_queries": [],
        "cooccurrence_product_ids": [],
        "cooccurrence_scores": [],
        "user_category_names": [],
    }
    if not _enabled():
        return empty

    lim = max(1, min(20, int(limit)))
    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            searched: list[dict[str, Any]] = []
            for row in session.run(
                """
                MATCH (u:User {id: $user_id})-[r:SEARCHED]->(q:Query)
                WITH q.text AS text, sum(coalesce(r.w, 1.0)) AS w
                RETURN text, w
                ORDER BY w DESC
                LIMIT $lim
                """,
                user_id=user_id,
                lim=lim,
            ):
                searched.append({"text": str(row["text"]), "weight": float(row["w"])})

            co_ids: list[int] = []
            co_scores: list[float] = []
            for row in session.run(
                """
                MATCH (me:User {id: $user_id})-[r1]->(p:Product)<-[r2]-(other:User)
                WHERE me <> other
                MATCH (other)-[r3]->(rec:Product)
                WHERE NOT (me)-[]->(rec)
                WITH rec, sum(coalesce(r3.w, 1.0)) AS score
                RETURN rec.id AS product_id, score
                ORDER BY score DESC
                LIMIT $lim
                """,
                user_id=user_id,
                lim=lim,
            ):
                co_ids.append(int(row["product_id"]))
                co_scores.append(float(row["score"]))

            cats: list[str] = []
            for row in session.run(
                """
                MATCH (u:User {id: $user_id})-[r]->(p:Product)-[:IN_CATEGORY]->(c:Category)
                WITH c.name AS name, sum(coalesce(r.w, 1.0)) AS w
                RETURN name, w
                ORDER BY w DESC
                LIMIT $lim
                """,
                user_id=user_id,
                lim=lim,
            ):
                n = row["name"]
                if n:
                    cats.append(str(n))

            return {
                "enabled": True,
                "searched_queries": searched,
                "cooccurrence_product_ids": co_ids,
                "cooccurrence_scores": co_scores,
                "user_category_names": list(dict.fromkeys(cats)),
            }
    except Exception:  # noqa: BLE001
        return empty
    finally:
        driver.close()
