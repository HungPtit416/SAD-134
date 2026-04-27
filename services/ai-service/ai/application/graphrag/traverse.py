from __future__ import annotations

from typing import Any

from django.conf import settings

try:
    from neo4j import GraphDatabase
except Exception:  # noqa: BLE001
    GraphDatabase = None  # type: ignore[assignment]


def _enabled() -> bool:
    return bool(getattr(settings, "NEO4J_URI", "")) and GraphDatabase is not None


TRAVERSE_CYPHER = """
// GraphRAG traverse: keep the subgraph compact and explainable.
// 1) Start from user
// 2) Expand to recent queries and their related products via co-search users
// 3) Expand to co-occurrence products, product-similarity, and categories

MATCH (me:User {id: $user_id})

// Recent searches for user
OPTIONAL MATCH (me)-[rs:SEARCHED]->(q:Query)
WITH me, q, coalesce(rs.w, 1.0) AS qw
ORDER BY qw DESC
WITH me, collect({text: q.text, w: qw})[0..$q_limit] AS qs

// Co-occurrence: users who share products with me, then their products
OPTIONAL MATCH (me)-[r1]->(p:Product)<-[r2]-(other:User)
WHERE me <> other
WITH me, qs, p, other, coalesce(r1.w,1.0) AS w1, coalesce(r2.w,1.0) AS w2
LIMIT $co_user_pairs_cap
OPTIONAL MATCH (other)-[r3]->(rec:Product)
WHERE NOT (me)-[]->(rec)
WITH me, qs,
     collect(DISTINCT {src:'co_user', other_id: other.id, seed_pid: p.id, rec_pid: rec.id, w: coalesce(r3.w,1.0)})[0..$co_limit] AS co_user_recs

// Similar-products: expand from user's interacted products via SIMILAR edges.
WITH me, qs, co_user_recs
OPTIONAL MATCH (me)-[]->(p3:Product)-[:SIMILAR]->(:Product)
WITH me, qs, co_user_recs, collect(DISTINCT p3.id) AS hist_sim_seeds
WITH me, qs, co_user_recs,
     CASE WHEN size(hist_sim_seeds) > 0 THEN hist_sim_seeds ELSE $seed_product_ids END AS sim_seed_ids
OPTIONAL MATCH (p3:Product)-[s:SIMILAR]->(sim:Product)
WHERE p3.id IN sim_seed_ids AND sim.id <> p3.id
WITH me, qs, co_user_recs,
     collect(DISTINCT {src:'similar', seed_pid: p3.id, rec_pid: sim.id, score: coalesce(s.score, 0.0), via: 'SIMILAR'})[0..$sim_limit] AS similar_recs

// Categories user has interacted with
OPTIONAL MATCH (me)-[r]->(p2:Product)-[:IN_CATEGORY]->(c:Category)
WITH me, qs, co_user_recs, similar_recs, c, sum(coalesce(r.w,1.0)) AS cw
ORDER BY cw DESC
WITH me, qs, co_user_recs, similar_recs, collect({id:c.id, name:c.name, w:cw})[0..$cat_limit] AS cats

RETURN qs AS searched_queries, co_user_recs AS co_user_recs, similar_recs AS similar_recs, cats AS user_categories;
"""


def traverse_subgraph(
    *,
    user_id: str,
    seed_product_ids: list[int] | None = None,
    q_limit: int = 6,
    co_limit: int = 30,
    sim_limit: int = 20,
    cat_limit: int = 6,
    co_user_pairs_cap: int = 400,
) -> dict[str, Any]:
    """
    Return a small, structured subgraph suitable for turning into evidence.
    """

    empty = {"enabled": False, "searched_queries": [], "co_user_recs": [], "similar_recs": [], "user_categories": []}
    if not _enabled():
        return empty

    q_limit = max(0, min(20, int(q_limit)))
    co_limit = max(0, min(200, int(co_limit)))
    sim_limit = max(0, min(200, int(sim_limit)))
    cat_limit = max(0, min(20, int(cat_limit)))
    co_user_pairs_cap = max(50, min(2000, int(co_user_pairs_cap)))
    seed_product_ids = [int(x) for x in (seed_product_ids or []) if x is not None][:50]

    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            row = session.run(
                TRAVERSE_CYPHER,
                user_id=user_id,
                seed_product_ids=seed_product_ids,
                q_limit=q_limit,
                co_limit=co_limit,
                sim_limit=sim_limit,
                cat_limit=cat_limit,
                co_user_pairs_cap=co_user_pairs_cap,
            ).single()
            if not row:
                return empty
            return {
                "enabled": True,
                "searched_queries": row.get("searched_queries") or [],
                "co_user_recs": row.get("co_user_recs") or [],
                "similar_recs": row.get("similar_recs") or [],
                "user_categories": row.get("user_categories") or [],
            }
    except Exception:  # noqa: BLE001
        return empty
    finally:
        driver.close()

