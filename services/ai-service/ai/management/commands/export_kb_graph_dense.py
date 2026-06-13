from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from ...application.product_gateway import list_products as list_catalog_products

try:
    from neo4j import GraphDatabase
except Exception:  # noqa: BLE001
    GraphDatabase = None  # type: ignore[assignment]


LIMIT_INTERACTIONS = 30
LIMIT_NEIGHBORS = 10
LIMIT_PRODUCTS = 30
LIMIT_SIMILAR = 50
LIMIT_CATEGORIES = 30


@dataclass(frozen=True)
class NodeRecord:
    label: str
    node_id: str
    display: str


@dataclass(frozen=True)
class EdgeRecord:
    source_key: str
    source_label: str
    source_id: str
    target_key: str
    target_label: str
    target_id: str
    rel_type: str
    weight: float
    props: dict[str, Any]


def _enabled() -> bool:
    return bool(getattr(settings, "NEO4J_URI", "")) and GraphDatabase is not None


def _cypher_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {_cypher_value(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_cypher_value(v) for v in value) + "]"
    text = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def _cypher_list(values: list[Any]) -> str:
    return "[" + ", ".join(_cypher_value(v) for v in values) + "]"


def _node_key(label: str, node_id: Any) -> str:
    return f"{label}:{node_id}"


def _node_display(label: str, row: dict[str, Any], prefix: str) -> str:
    if label == "User":
        return str(row.get(f"{prefix}_id") or row.get(f"{prefix}_display") or "")
    if label == "Product":
        return str(row.get(f"{prefix}_display") or row.get(f"{prefix}_name") or row.get(f"{prefix}_sku") or row.get(f"{prefix}_id") or "")
    if label == "Category":
        return str(row.get(f"{prefix}_display") or row.get(f"{prefix}_name") or row.get(f"{prefix}_id") or "")
    if label == "Query":
        return str(row.get(f"{prefix}_display") or row.get(f"{prefix}_text") or "")
    return str(row.get(f"{prefix}_display") or row.get(f"{prefix}_id") or "")


def _node_from_row(row: dict[str, Any], prefix: str) -> NodeRecord:
    label = str(row.get(f"{prefix}_label") or "")
    node_id = str(row.get(f"{prefix}_id") or "")
    display = _node_display(label, row, prefix)
    return NodeRecord(label=label, node_id=node_id, display=display)


def _add_node(nodes: dict[str, NodeRecord], node: NodeRecord) -> str:
    if not node.label or not node.node_id:
        return ""
    key = _node_key(node.label, node.node_id)
    nodes.setdefault(key, node)
    return key


def _add_edge(edges: dict[tuple[str, str, str], EdgeRecord], edge: EdgeRecord) -> None:
    if not edge.source_key or not edge.target_key or not edge.rel_type:
        return
    key = (edge.source_key, edge.rel_type, edge.target_key)
    prev = edges.get(key)
    if prev is None:
        edges[key] = edge
        return
    merged = EdgeRecord(
        source_key=prev.source_key,
        source_label=prev.source_label,
        source_id=prev.source_id,
        target_key=prev.target_key,
        target_label=prev.target_label,
        target_id=prev.target_id,
        rel_type=prev.rel_type,
        weight=max(prev.weight, edge.weight),
        props=prev.props or edge.props,
    )
    edges[key] = merged


def _edge_from_row(row: dict[str, Any]) -> EdgeRecord:
    src = _node_from_row(row, "src")
    dst = _node_from_row(row, "dst")
    try:
        weight = float(row.get("weight") or 1.0)
    except Exception:  # noqa: BLE001
        weight = 1.0
    props = row.get("props") or {}
    if isinstance(props, str):
        try:
            props = json.loads(props)
        except Exception:  # noqa: BLE001
            props = {"raw": props}
    return EdgeRecord(
        source_key=_node_key(src.label, src.node_id),
        source_label=src.label,
        source_id=src.node_id,
        target_key=_node_key(dst.label, dst.node_id),
        target_label=dst.label,
        target_id=dst.node_id,
        rel_type=str(row.get("rel_type") or ""),
        weight=weight,
        props=dict(props or {}),
    )


def _run(session, cypher: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in session.run(cypher, **params)]


DIRECT_PRODUCT_CYPHER = """
MATCH (u:User {id: $user_id})-[r]->(p:Product)
WHERE type(r) IN ['VIEWED', 'CLICKED', 'ADDED_TO_CART', 'PURCHASED']
RETURN
  'User' AS src_label,
  u.id AS src_id,
  coalesce(u.id, u.email, toString(u.id)) AS src_display,
  'Product' AS dst_label,
  p.id AS dst_id,
  coalesce(p.name, p.sku, toString(p.id)) AS dst_display,
  type(r) AS rel_type,
  coalesce(r.w, 1.0) AS weight,
  properties(r) AS props
ORDER BY weight DESC
LIMIT $limit
"""

DIRECT_QUERY_CYPHER = """
MATCH (u:User {id: $user_id})-[r:SEARCHED]->(q:Query)
RETURN
  'User' AS src_label,
  u.id AS src_id,
  coalesce(u.id, u.email, toString(u.id)) AS src_display,
  'Query' AS dst_label,
  q.text AS dst_id,
  coalesce(q.text, q.id, q.text) AS dst_display,
  type(r) AS rel_type,
  coalesce(r.w, 1.0) AS weight,
  properties(r) AS props
ORDER BY weight DESC
LIMIT $limit
"""

NEIGHBOR_USERS_CYPHER = """
MATCH (u:User {id: $user_id})-[r1]->(:Product)<-[r2]-(other:User)
WHERE type(r1) IN ['VIEWED', 'CLICKED', 'ADDED_TO_CART', 'PURCHASED']
  AND type(r2) IN ['VIEWED', 'CLICKED', 'ADDED_TO_CART', 'PURCHASED']
WHERE other.id <> $user_id
RETURN other.id AS other_id, count(*) AS shared_count
ORDER BY shared_count DESC, other_id
LIMIT $limit
"""

PRODUCT_CATEGORY_CYPHER = """
UNWIND $product_ids AS pid
MATCH (p:Product {id: pid})-[r:IN_CATEGORY]->(c:Category)
RETURN
  'Product' AS src_label,
  p.id AS src_id,
  coalesce(p.name, p.sku, toString(p.id)) AS src_display,
  'Category' AS dst_label,
  c.id AS dst_id,
  coalesce(c.name, toString(c.id)) AS dst_display,
  type(r) AS rel_type,
  1.0 AS weight,
  properties(r) AS props
ORDER BY dst_display, src_display
LIMIT $limit
"""

PRODUCT_SIMILAR_CYPHER = """
UNWIND $product_ids AS pid
MATCH (p:Product {id: pid})-[r:SIMILAR]->(s:Product)
RETURN
  'Product' AS src_label,
  p.id AS src_id,
  coalesce(p.name, p.sku, toString(p.id)) AS src_display,
  'Product' AS dst_label,
  s.id AS dst_id,
  coalesce(s.name, s.sku, toString(s.id)) AS dst_display,
  type(r) AS rel_type,
  coalesce(r.score, 1.0) AS weight,
  properties(r) AS props
ORDER BY weight DESC
LIMIT $limit
"""

CATEGORY_PEER_PRODUCTS_CYPHER = """
UNWIND $category_ids AS cid
MATCH (peer:Product)-[r:IN_CATEGORY]->(c:Category {id: cid})
WHERE NOT peer.id IN $exclude_product_ids
RETURN
  'Product' AS src_label,
  peer.id AS src_id,
  coalesce(peer.name, peer.sku, toString(peer.id)) AS src_display,
  'Category' AS dst_label,
  c.id AS dst_id,
  coalesce(c.name, toString(c.id)) AS dst_display,
  type(r) AS rel_type,
  1.0 AS weight,
  properties(r) AS props
ORDER BY dst_display, src_display
LIMIT $limit
"""

NEIGHBOR_PRODUCT_CYPHER = """
MATCH (other:User {id: $other_id})-[r]->(p:Product)
WHERE type(r) IN ['VIEWED', 'CLICKED', 'ADDED_TO_CART', 'PURCHASED']
RETURN
  'User' AS src_label,
  other.id AS src_id,
  coalesce(other.id, other.email, toString(other.id)) AS src_display,
  'Product' AS dst_label,
  p.id AS dst_id,
  coalesce(p.name, p.sku, toString(p.id)) AS dst_display,
  type(r) AS rel_type,
  coalesce(r.w, 1.0) AS weight,
  properties(r) AS props
ORDER BY weight DESC
LIMIT $limit
"""

NEIGHBOR_QUERY_CYPHER = """
MATCH (other:User {id: $other_id})-[r:SEARCHED]->(q:Query)
RETURN
  'User' AS src_label,
  other.id AS src_id,
  coalesce(other.id, other.email, toString(other.id)) AS src_display,
  'Query' AS dst_label,
  q.text AS dst_id,
  coalesce(q.text, q.id, q.text) AS dst_display,
  type(r) AS rel_type,
  coalesce(r.w, 1.0) AS weight,
  properties(r) AS props
ORDER BY weight DESC
LIMIT $limit
"""


class Command(BaseCommand):
    help = "Export a dense Neo4j subgraph CSV + Cypher around one user for report screenshots."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=str, default="user-0001")
        parser.add_argument("--limit", type=int, default=LIMIT_INTERACTIONS)
        parser.add_argument("--neighbor-limit", type=int, default=LIMIT_NEIGHBORS)
        parser.add_argument("--product-limit", type=int, default=LIMIT_PRODUCTS)
        parser.add_argument("--similar-limit", type=int, default=LIMIT_SIMILAR)
        parser.add_argument("--category-limit", type=int, default=LIMIT_CATEGORIES)
        parser.add_argument(
            "--showcase",
            action="store_true",
            help="Generate a self-contained dense showcase Cypher that seeds 2-3 demo users, ratings, and a category hub.",
        )
        parser.add_argument("--out-dir", type=str, default=str(Path("/app/reports")))

    def handle(self, *args, **opts):
        if not _enabled():
            raise SystemExit("Neo4j is not configured (NEO4J_URI missing or neo4j driver not installed).")

        user_id = str(opts["user_id"])
        limit = max(1, min(200, int(opts["limit"])))
        neighbor_limit = max(1, min(50, int(opts["neighbor_limit"])))
        product_limit = max(1, min(100, int(opts["product_limit"])))
        similar_limit = max(1, min(200, int(opts["similar_limit"])))
        category_limit = max(1, min(100, int(opts["category_limit"])))
        showcase = bool(opts["showcase"])

        out_dir = Path(str(opts["out_dir"]))
        out_dir.mkdir(parents=True, exist_ok=True)

        nodes: dict[str, NodeRecord] = {}
        edges: dict[tuple[str, str, str], EdgeRecord] = {}

        direct_product_ids: list[int] = []
        focus_category_ids: list[int] = []
        direct_query_texts: list[str] = []
        neighbor_ids: list[str] = []

        driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
        try:
            with driver.session() as session:
                for row in _run(session, DIRECT_PRODUCT_CYPHER, user_id=user_id, limit=limit):
                    edge = _edge_from_row(row)
                    src = _node_from_row(row, "src")
                    dst = _node_from_row(row, "dst")
                    _add_node(nodes, src)
                    _add_node(nodes, dst)
                    _add_edge(edges, edge)
                    try:
                        direct_product_ids.append(int(dst.node_id))
                    except Exception:  # noqa: BLE001
                        pass

                for row in _run(session, DIRECT_QUERY_CYPHER, user_id=user_id, limit=limit):
                    edge = _edge_from_row(row)
                    src = _node_from_row(row, "src")
                    dst = _node_from_row(row, "dst")
                    _add_node(nodes, src)
                    _add_node(nodes, dst)
                    _add_edge(edges, edge)
                    direct_query_texts.append(str(dst.node_id))

                if direct_product_ids:
                    for row in _run(session, PRODUCT_CATEGORY_CYPHER, product_ids=direct_product_ids, limit=category_limit):
                        edge = _edge_from_row(row)
                        src = _node_from_row(row, "src")
                        dst = _node_from_row(row, "dst")
                        _add_node(nodes, src)
                        _add_node(nodes, dst)
                        _add_edge(edges, edge)
                        try:
                            focus_category_ids.append(int(dst.node_id))
                        except Exception:  # noqa: BLE001
                            pass

                    for row in _run(session, PRODUCT_SIMILAR_CYPHER, product_ids=direct_product_ids, limit=similar_limit):
                        edge = _edge_from_row(row)
                        src = _node_from_row(row, "src")
                        dst = _node_from_row(row, "dst")
                        _add_node(nodes, src)
                        _add_node(nodes, dst)
                        _add_edge(edges, edge)
                        try:
                            if dst.node_id.isdigit():
                                direct_product_ids.append(int(dst.node_id))
                        except Exception:  # noqa: BLE001
                            pass

                neighbor_rows = _run(session, NEIGHBOR_USERS_CYPHER, user_id=user_id, limit=neighbor_limit)
                for row in neighbor_rows:
                    nid = str(row.get("other_id") or "").strip()
                    if nid:
                        neighbor_ids.append(nid)

                neighbor_product_ids: list[int] = []
                for nid in neighbor_ids:
                    for row in _run(session, NEIGHBOR_PRODUCT_CYPHER, other_id=nid, limit=product_limit):
                        edge = _edge_from_row(row)
                        dst = _node_from_row(row, "dst")
                        _add_node(nodes, _node_from_row(row, "src"))
                        _add_node(nodes, dst)
                        _add_edge(edges, edge)
                        try:
                            neighbor_product_ids.append(int(dst.node_id))
                        except Exception:  # noqa: BLE001
                            pass

                    for row in _run(session, NEIGHBOR_QUERY_CYPHER, other_id=nid, limit=limit):
                        edge = _edge_from_row(row)
                        _add_node(nodes, _node_from_row(row, "src"))
                        _add_node(nodes, _node_from_row(row, "dst"))
                        _add_edge(edges, edge)
                        direct_query_texts.append(str(row.get("dst_id") or ""))

                focus_product_ids = sorted(
                    {pid for pid in direct_product_ids + neighbor_product_ids if isinstance(pid, int)}
                )
                if focus_product_ids:
                    for row in _run(session, PRODUCT_CATEGORY_CYPHER, product_ids=focus_product_ids, limit=category_limit):
                        edge = _edge_from_row(row)
                        _add_node(nodes, _node_from_row(row, "src"))
                        _add_node(nodes, _node_from_row(row, "dst"))
                        _add_edge(edges, edge)
                        try:
                            focus_category_ids.append(int(row.get("dst_id") or 0))
                        except Exception:  # noqa: BLE001
                            pass

                    for row in _run(session, PRODUCT_SIMILAR_CYPHER, product_ids=focus_product_ids, limit=similar_limit):
                        edge = _edge_from_row(row)
                        _add_node(nodes, _node_from_row(row, "src"))
                        _add_node(nodes, _node_from_row(row, "dst"))
                        _add_edge(edges, edge)
                        try:
                            if str(row.get("dst_id") or "").isdigit():
                                focus_product_ids.append(int(row["dst_id"]))
                        except Exception:  # noqa: BLE001
                            pass

                focus_category_ids = sorted({cid for cid in focus_category_ids if isinstance(cid, int)})
                if focus_category_ids:
                    category_peer_product_ids: list[int] = []
                    for row in _run(
                        session,
                        CATEGORY_PEER_PRODUCTS_CYPHER,
                        category_ids=focus_category_ids,
                        exclude_product_ids=focus_product_ids,
                        limit=product_limit,
                    ):
                        edge = _edge_from_row(row)
                        src = _node_from_row(row, "src")
                        dst = _node_from_row(row, "dst")
                        _add_node(nodes, src)
                        _add_node(nodes, dst)
                        _add_edge(edges, edge)
                        try:
                            category_peer_product_ids.append(int(src.node_id))
                        except Exception:  # noqa: BLE001
                            pass

                    focus_product_ids = sorted(
                        {
                            pid
                            for pid in (focus_product_ids + category_peer_product_ids)
                            if isinstance(pid, int)
                        }
                    )

                    if category_peer_product_ids:
                        for row in _run(session, PRODUCT_CATEGORY_CYPHER, product_ids=category_peer_product_ids, limit=category_limit):
                            edge = _edge_from_row(row)
                            src = _node_from_row(row, "src")
                            dst = _node_from_row(row, "dst")
                            _add_node(nodes, src)
                            _add_node(nodes, dst)
                            _add_edge(edges, edge)
                            try:
                                focus_category_ids.append(int(dst.node_id))
                            except Exception:  # noqa: BLE001
                                pass

                        for row in _run(session, PRODUCT_SIMILAR_CYPHER, product_ids=category_peer_product_ids, limit=similar_limit):
                            edge = _edge_from_row(row)
                            _add_node(nodes, _node_from_row(row, "src"))
                            _add_node(nodes, _node_from_row(row, "dst"))
                            _add_edge(edges, edge)
                            try:
                                if str(row.get("dst_id") or "").isdigit():
                                    focus_product_ids.append(int(row["dst_id"]))
                            except Exception:  # noqa: BLE001
                                pass

                focus_product_ids = sorted({pid for pid in focus_product_ids if isinstance(pid, int)})
                neighbor_ids = list(dict.fromkeys(nid for nid in neighbor_ids if nid))

                # Deduplicate and trim query texts for the Cypher file.
                query_texts = []
                seen_q = set()
                for q in direct_query_texts:
                    q = str(q).strip()
                    if not q or q in seen_q:
                        continue
                    seen_q.add(q)
                    query_texts.append(q)

                if showcase:
                    catalog = list_catalog_products()
                    catalog_payload = _build_catalog_payload(catalog)
                    hub_category_ids = _build_hub_category_ids(catalog, max(2, min(4, category_limit // 10 + 1)))
                    showcase_products = _build_showcase_product_ids(catalog, min(30, max(20, product_limit)))
                    showcase_query_texts = _build_showcase_queries(catalog, query_texts)
                    demo_users = [f"report-user-{i}" for i in range(1, 4)]
                    interactions = _build_demo_interactions(demo_users, showcase_products)
                    ratings = _build_demo_ratings(demo_users, showcase_products)
                    similar_pairs = _build_demo_similarity_pairs(showcase_products)

                    dense_cypher = SHOWCASE_CYPHER_TEMPLATE.format(
                        user_id=_cypher_value(user_id),
                        demo_users=_cypher_value(demo_users),
                        showcase_queries=_cypher_value(showcase_query_texts),
                        catalog_products=_cypher_value(catalog_payload),
                        hub_category_ids=_cypher_value(hub_category_ids),
                        demo_interactions=_cypher_value(interactions),
                        demo_ratings=_cypher_value(ratings),
                        demo_similar_pairs=_cypher_value(similar_pairs),
                    )
                else:
                    # Build a dense visualization query with literal lists for Neo4j Browser.
                    dense_cypher = DENSE_CYPHER_TEMPLATE.format(
                        user_id=_cypher_value(user_id),
                        product_ids=_cypher_list(focus_product_ids[: max(1, category_limit * 2)]),
                        neighbor_ids=_cypher_list(neighbor_ids[:neighbor_limit]),
                        query_texts=_cypher_list(query_texts[:limit]),
                        interaction_limit=limit,
                        category_limit=category_limit,
                        similar_limit=similar_limit,
                        product_limit=product_limit,
                    )

        finally:
            driver.close()

        out_nodes = out_dir / "kb_graph_dense_nodes.csv"
        out_edges = out_dir / "kb_graph_dense_edges.csv"
        out_cypher = out_dir / "kb_graph_dense_visualize.cypher"

        with out_nodes.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["node_key", "label", "node_id", "display"])
            w.writeheader()
            for key in sorted(nodes):
                node = nodes[key]
                w.writerow(
                    {
                        "node_key": key,
                        "label": node.label,
                        "node_id": node.node_id,
                        "display": node.display,
                    }
                )

        with out_edges.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "source_key",
                    "source_label",
                    "source_id",
                    "rel_type",
                    "target_key",
                    "target_label",
                    "target_id",
                    "weight",
                    "props",
                ],
            )
            w.writeheader()
            for key in sorted(edges):
                edge = edges[key]
                w.writerow(
                    {
                        "source_key": edge.source_key,
                        "source_label": edge.source_label,
                        "source_id": edge.source_id,
                        "rel_type": edge.rel_type,
                        "target_key": edge.target_key,
                        "target_label": edge.target_label,
                        "target_id": edge.target_id,
                        "weight": round(float(edge.weight), 4),
                        "props": json.dumps(edge.props, ensure_ascii=False, sort_keys=True),
                    }
                )

        out_cypher.write_text(dense_cypher, encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Wrote dense nodes CSV: {out_nodes}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote dense edges CSV: {out_edges}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote dense visualize Cypher: {out_cypher}"))


def _build_catalog_payload(products: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in products:
        out.append(
            {
                "id": int(p.id),
                "sku": str(p.sku or ""),
                "name": str(p.name or ""),
                "main_category": str(p.main_category or ""),
                "price": str(p.price or ""),
                "currency": str(p.currency or ""),
                "image": str(p.image or ""),
                "ratings": float(p.ratings) if p.ratings is not None else 0.0,
                "no_of_ratings": int(p.no_of_ratings) if p.no_of_ratings is not None else 0,
                "category_id": int(p.category_id) if p.category_id is not None else None,
                "category_name": str(p.category_name or ""),
                "description": str(p.description or ""),
            }
        )
    return out


def _build_hub_category_ids(products: list[Any], limit: int) -> list[int]:
    counts: dict[int, int] = {}
    for p in products:
        if p.category_id is None:
            continue
        counts[int(p.category_id)] = counts.get(int(p.category_id), 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [cid for cid, _ in ordered[: max(1, limit)]]


def _build_showcase_product_ids(products: list[Any], limit: int) -> list[int]:
    counts: dict[int, int] = {}
    for p in products:
        if p.category_id is None:
            continue
        counts[int(p.category_id)] = counts.get(int(p.category_id), 0) + 1
    hub_id = max(counts.items(), key=lambda item: (item[1], -item[0]))[0] if counts else None
    hub: list[int] = []
    rest: list[int] = []
    for p in products:
        if hub_id is not None and p.category_id == hub_id:
            hub.append(int(p.id))
        else:
            rest.append(int(p.id))
    ordered = hub + rest
    return ordered[: max(1, limit)]


def _build_showcase_queries(products: list[Any], existing: list[str]) -> list[str]:
    categories: list[str] = []
    for p in products:
        cname = str(p.category_name or "").strip()
        if cname and cname not in categories:
            categories.append(cname)
    base = [
        "best sellers",
        "top rated products",
        "cheap deals",
        "compare similar products",
        "new arrivals",
    ]
    for cname in categories[:5]:
        base.extend(
            [
                f"{cname} hot deals",
                f"best {cname.lower()}",
            ]
        )
    for q in existing:
        q = str(q).strip()
        if q and q not in base:
            base.append(q)
    return base[:12]


def _build_demo_interactions(users: list[str], product_ids: list[int]) -> list[dict[str, Any]]:
    rel_cycle = ["VIEWED", "CLICKED", "ADDED_TO_CART", "PURCHASED"]
    out: list[dict[str, Any]] = []
    for ui, uid in enumerate(users):
        for pi, pid in enumerate(product_ids):
            rel = rel_cycle[(ui + pi) % len(rel_cycle)]
            out.append(
                {
                    "user_id": uid,
                    "product_id": pid,
                    "rel": rel,
                    "w": [1.0, 2.0, 5.0, 10.0][(ui + pi) % len(rel_cycle)],
                }
            )
    return out


def _build_demo_ratings(users: list[str], product_ids: list[int]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    slice_ids = product_ids[: min(len(product_ids), 15)]
    for ui, uid in enumerate(users):
        for pi, pid in enumerate(slice_ids):
            stars = ((ui + pi) % 5) + 1
            out.append(
                {
                    "key": f"{uid}::{pid}",
                    "user_id": uid,
                    "product_id": pid,
                    "stars": stars,
                }
            )
    return out


def _build_demo_similarity_pairs(product_ids: list[int]) -> list[dict[str, Any]]:
    ids = product_ids[: min(len(product_ids), 25)]
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if i == j:
                continue
            score = round(0.95 - abs(i - j) * 0.01, 3)
            if score < 0.35:
                score = 0.35
            pairs.append({"a": a, "b": b, "score": score})
    return pairs


SHOWCASE_CYPHER_TEMPLATE = """
// Self-contained showcase graph for Neo4j Browser.
// This seeds a dense, report-friendly graph with demo users, product ratings,
// category hubs, queries, and a similarity mesh among products.

:param user_id => {user_id};
:param demo_users => {demo_users};
:param showcase_queries => {showcase_queries};
:param catalog_products => {catalog_products};
:param hub_category_ids => {hub_category_ids};
:param demo_interactions => {demo_interactions};
:param demo_ratings => {demo_ratings};
:param demo_similar_pairs => {demo_similar_pairs};

UNWIND $catalog_products AS prod
MERGE (p:Product {{id: prod.id}})
SET
  p.sku = prod.sku,
  p.name = prod.name,
  p.main_category = prod.main_category,
  p.price = prod.price,
  p.currency = prod.currency,
  p.image = prod.image,
  p.ratings = prod.ratings,
  p.no_of_ratings = prod.no_of_ratings,
  p.description = prod.description
WITH p, prod
FOREACH (_ IN CASE WHEN prod.category_id IS NULL THEN [] ELSE [1] END |
  MERGE (c:Category {{id: prod.category_id}})
  SET c.name = prod.category_name
  MERGE (p)-[:IN_CATEGORY]->(c)
)

UNWIND $hub_category_ids AS cid
MERGE (hub:Category {{id: cid}})

UNWIND $demo_users AS uid
MERGE (u:User {{id: uid}})

UNWIND $showcase_queries AS qtext
MERGE (q:Query {{text: qtext}})

UNWIND $demo_interactions AS row
MATCH (u:User {{id: row.user_id}}), (p:Product {{id: row.product_id}})
FOREACH (_ IN CASE WHEN row.rel = 'VIEWED' THEN [1] ELSE [] END |
  MERGE (u)-[r:VIEWED]->(p)
  SET r.w = row.w
)
FOREACH (_ IN CASE WHEN row.rel = 'CLICKED' THEN [1] ELSE [] END |
  MERGE (u)-[r:CLICKED]->(p)
  SET r.w = row.w
)
FOREACH (_ IN CASE WHEN row.rel = 'ADDED_TO_CART' THEN [1] ELSE [] END |
  MERGE (u)-[r:ADDED_TO_CART]->(p)
  SET r.w = row.w
)
FOREACH (_ IN CASE WHEN row.rel = 'PURCHASED' THEN [1] ELSE [] END |
  MERGE (u)-[r:PURCHASED]->(p)
  SET r.w = row.w
)

UNWIND $demo_ratings AS row
MATCH (u:User {{id: row.user_id}}), (p:Product {{id: row.product_id}})
MERGE (pr:ProductRating {{key: row.key}})
SET
  pr.user_id = row.user_id,
  pr.product_id = row.product_id,
  pr.stars = row.stars,
  pr.created_at = datetime(),
  pr.updated_at = datetime()
MERGE (u)-[:RATED]->(pr)
MERGE (pr)-[:OF_PRODUCT]->(p)

UNWIND $demo_similar_pairs AS row
MATCH (a:Product {{id: row.a}}), (b:Product {{id: row.b}})
MERGE (a)-[r:SIMILAR]->(b)
SET r.score = row.score

WITH $demo_users AS demo_users
MATCH (u:User)
WHERE u.id IN demo_users
OPTIONAL MATCH (u)-[ru:VIEWED|CLICKED|ADDED_TO_CART|PURCHASED|SEARCHED|RATED]->(x)
OPTIONAL MATCH (x)-[rx:IN_CATEGORY|SIMILAR|OF_PRODUCT]->(y)
OPTIONAL MATCH (x)-[:IN_CATEGORY]->(c:Category)
RETURN u, ru, x, rx, y, c
LIMIT 1000;
"""
DENSE_CYPHER_TEMPLATE = """
// Dense Neo4j visualization for the report.
// Run in Neo4j Browser, then screenshot the rendered graph.
// Parameters are baked into the file so the query is copy-paste ready.

:param user_id => {user_id};
:param product_ids => {product_ids};
:param neighbor_ids => {neighbor_ids};
:param query_texts => {query_texts};

MATCH (me:User {{id: $user_id}})

OPTIONAL MATCH (me)-[r0]->(p:Product)
WHERE type(r0) IN ['VIEWED', 'CLICKED', 'ADDED_TO_CART', 'PURCHASED']
WHERE p.id IN $product_ids
WITH me, collect(DISTINCT p)[0..{interaction_limit}] AS seed_products, collect(DISTINCT r0)[0..{interaction_limit}] AS seed_rels

OPTIONAL MATCH (me)-[rq:SEARCHED]->(q:Query)
WHERE q.text IN $query_texts
WITH me, seed_products, seed_rels, collect(DISTINCT q)[0..{interaction_limit}] AS seed_queries, collect(DISTINCT rq)[0..{interaction_limit}] AS seed_query_rels

UNWIND seed_products AS p
OPTIONAL MATCH (p)-[pc:IN_CATEGORY]->(c:Category)
OPTIONAL MATCH (p)-[ps:SIMILAR]->(s:Product)
WITH me, seed_products, seed_rels, seed_queries, seed_query_rels,
     collect(DISTINCT c)[0..{category_limit}] AS seed_categories,
     collect(DISTINCT pc)[0..{category_limit}] AS seed_category_rels,
     collect(DISTINCT s)[0..{similar_limit}] AS seed_similars,
     collect(DISTINCT ps)[0..{similar_limit}] AS seed_similarity_rels

OPTIONAL MATCH (me)-[r1]->(shared:Product)<-[r2]-(other:User)
WHERE type(r1) IN ['VIEWED', 'CLICKED', 'ADDED_TO_CART', 'PURCHASED']
  AND type(r2) IN ['VIEWED', 'CLICKED', 'ADDED_TO_CART', 'PURCHASED']
WHERE other.id IN $neighbor_ids
WITH me, seed_products, seed_rels, seed_queries, seed_query_rels, seed_categories, seed_category_rels, seed_similars, seed_similarity_rels,
     collect(DISTINCT other)[0..{interaction_limit}] AS neighbor_users,
     collect(DISTINCT shared)[0..{interaction_limit}] AS shared_products,
     collect(DISTINCT r1)[0..{interaction_limit}] AS shared_rels_out,
     collect(DISTINCT r2)[0..{interaction_limit}] AS shared_rels_in

UNWIND neighbor_users AS other
OPTIONAL MATCH (other)-[ro]->(op:Product)
WHERE type(ro) IN ['VIEWED', 'CLICKED', 'ADDED_TO_CART', 'PURCHASED']
WHERE op.id IN $product_ids
OPTIONAL MATCH (other)-[roq:SEARCHED]->(oq:Query)
WHERE oq.text IN $query_texts
OPTIONAL MATCH (op)-[opc:IN_CATEGORY]->(oc:Category)
OPTIONAL MATCH (op)-[ops:SIMILAR]->(os:Product)
WITH me, seed_products, seed_rels, seed_queries, seed_query_rels, seed_categories, seed_category_rels, seed_similars, seed_similarity_rels,
     neighbor_users, shared_products, shared_rels_out, shared_rels_in,
     collect(DISTINCT op)[0..{product_limit}] AS neighbor_products,
     collect(DISTINCT oq)[0..{interaction_limit}] AS neighbor_queries,
     collect(DISTINCT oc)[0..{category_limit}] AS neighbor_categories,
     collect(DISTINCT os)[0..{similar_limit}] AS neighbor_similars,
     collect(DISTINCT ro)[0..{product_limit}] AS neighbor_product_rels,
     collect(DISTINCT roq)[0..{interaction_limit}] AS neighbor_query_rels,
     collect(DISTINCT opc)[0..{category_limit}] AS neighbor_category_rels,
     collect(DISTINCT ops)[0..{similar_limit}] AS neighbor_similarity_rels

RETURN
  me,
  seed_products,
  seed_queries,
  seed_categories,
  seed_similars,
  neighbor_users,
  shared_products,
  neighbor_products,
  neighbor_queries,
  neighbor_categories,
  neighbor_similars,
  seed_rels,
  seed_query_rels,
  seed_category_rels,
  seed_similarity_rels,
  shared_rels_out,
  shared_rels_in,
  neighbor_product_rels,
  neighbor_query_rels,
  neighbor_category_rels,
  neighbor_similarity_rels;
"""
