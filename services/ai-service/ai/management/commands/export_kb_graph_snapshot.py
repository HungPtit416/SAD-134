from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

try:
    from neo4j import GraphDatabase
except Exception:  # noqa: BLE001
    GraphDatabase = None  # type: ignore[assignment]


KB_LABELS = {"User", "Product", "Category", "Query", "ProductRating"}


def _enabled() -> bool:
    return bool(getattr(settings, "NEO4J_URI", "")) and GraphDatabase is not None


def _cypher_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def _props_json(props: dict[str, Any]) -> str:
    return json.dumps(props or {}, ensure_ascii=False, sort_keys=True)


def _display_for_node(labels: list[str], props: dict[str, Any], neo_id: int) -> str:
    label_set = set(labels)
    if "User" in label_set:
        return str(props.get("id") or props.get("email") or neo_id)
    if "Product" in label_set:
        return str(props.get("name") or props.get("sku") or props.get("id") or neo_id)
    if "Category" in label_set:
        return str(props.get("name") or props.get("slug") or props.get("id") or neo_id)
    if "Query" in label_set:
        return str(props.get("text") or neo_id)
    if "ProductRating" in label_set:
        return str(props.get("key") or f"{props.get('user_id')}-{props.get('product_id')}" or neo_id)
    return str(props.get("name") or props.get("id") or neo_id)


def _node_key(labels: list[str], props: dict[str, Any], neo_id: int) -> str:
    label_set = set(labels)
    if "User" in label_set:
        return f"User:{props.get('id', neo_id)}"
    if "Product" in label_set:
        return f"Product:{props.get('id', neo_id)}"
    if "Category" in label_set:
        return f"Category:{props.get('id', neo_id)}"
    if "Query" in label_set:
        return f"Query:{props.get('text', neo_id)}"
    if "ProductRating" in label_set:
        return f"ProductRating:{props.get('key', neo_id)}"
    primary = labels[0] if labels else "Node"
    return f"{primary}:{neo_id}"


class Command(BaseCommand):
    help = "Export the current KB graph from Neo4j into CSV snapshot files."

    def add_arguments(self, parser):
        parser.add_argument("--out-dir", type=str, default=str(Path("/app/reports")))
        parser.add_argument("--labels", type=str, default="User,Product,Category,Query,ProductRating")

    def handle(self, *args, **opts):
        if not _enabled():
            raise SystemExit("Neo4j is not configured (NEO4J_URI missing or neo4j driver not installed).")

        out_dir = Path(str(opts["out_dir"]))
        out_dir.mkdir(parents=True, exist_ok=True)

        allowed_labels = {x.strip() for x in str(opts["labels"]).split(",") if x.strip()}
        allowed_labels = allowed_labels or KB_LABELS

        driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
        rows: list[dict[str, Any]] = []
        try:
            with driver.session() as session:
                node_rows = session.run(
                    """
                    MATCH (n)
                    WHERE any(l IN labels(n) WHERE l IN $labels)
                    RETURN id(n) AS neo_id, labels(n) AS labels, properties(n) AS props
                    ORDER BY labels(n), coalesce(n.id, n.text, n.key, toString(id(n)))
                    """,
                    labels=sorted(allowed_labels),
                )
                for row in node_rows:
                    neo_id = int(row["neo_id"])
                    labels = list(row["labels"] or [])
                    props = dict(row["props"] or {})
                    rows.append(
                        {
                            "row_type": "NODE",
                            "node_key": _node_key(labels, props, neo_id),
                            "neo_id": neo_id,
                            "labels": "|".join(labels),
                            "source_key": "",
                            "source_props": "",
                            "source_labels": "",
                            "target_key": "",
                            "target_props": "",
                            "target_labels": "",
                            "rel_type": "",
                            "display": _display_for_node(labels, props, neo_id),
                            "props": _props_json(props),
                        }
                    )

                edge_rows = session.run(
                    """
                    MATCH (a)-[r]->(b)
                    WHERE any(l IN labels(a) WHERE l IN $labels)
                      AND any(l IN labels(b) WHERE l IN $labels)
                    RETURN
                      id(a) AS src_neo_id,
                      labels(a) AS src_labels,
                      properties(a) AS src_props,
                      id(b) AS dst_neo_id,
                      labels(b) AS dst_labels,
                      properties(b) AS dst_props,
                      type(r) AS rel_type,
                      properties(r) AS props
                    ORDER BY type(r), id(a), id(b)
                    """,
                    labels=sorted(allowed_labels),
                )

                for row in edge_rows:
                    src_neo_id = int(row["src_neo_id"])
                    dst_neo_id = int(row["dst_neo_id"])
                    src_labels = list(row["src_labels"] or [])
                    dst_labels = list(row["dst_labels"] or [])
                    src_props = dict(row["src_props"] or {})
                    dst_props = dict(row["dst_props"] or {})
                    rows.append(
                        {
                            "row_type": "EDGE",
                            "node_key": "",
                            "neo_id": "",
                            "labels": "",
                            "source_key": _node_key(src_labels, src_props, src_neo_id),
                            "source_neo_id": src_neo_id,
                            "source_labels": "|".join(src_labels),
                            "source_props": _props_json(src_props),
                            "target_key": _node_key(dst_labels, dst_props, dst_neo_id),
                            "target_neo_id": dst_neo_id,
                            "target_labels": "|".join(dst_labels),
                            "target_props": _props_json(dst_props),
                            "rel_type": str(row["rel_type"]),
                            "display": "",
                            "props": _props_json(dict(row["props"] or {})),
                        }
                    )
        finally:
            driver.close()

        out_csv = out_dir / "kb_graph_snapshot.csv"

        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "row_type",
                    "node_key",
                    "neo_id",
                    "labels",
                    "source_key",
                    "source_neo_id",
                    "source_labels",
                    "source_props",
                    "target_key",
                    "target_neo_id",
                    "target_labels",
                    "target_props",
                    "rel_type",
                    "display",
                    "props",
                ],
            )
            w.writeheader()
            for row in rows:
                w.writerow(row)

        node_count = sum(1 for r in rows if r["row_type"] == "NODE")
        edge_count = sum(1 for r in rows if r["row_type"] == "EDGE")
        self.stdout.write(self.style.SUCCESS(f"Wrote snapshot CSV: {out_csv}"))
        self.stdout.write(self.style.SUCCESS(f"Snapshot counts: nodes={node_count}, edges={edge_count}"))
