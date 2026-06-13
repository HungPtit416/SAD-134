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


ALLOWED_LABELS = {"User", "Product", "Category", "Query", "ProductRating"}
ALLOWED_REL_TYPES = {"VIEWED", "CLICKED", "ADDED_TO_CART", "PURCHASED", "SEARCHED", "IN_CATEGORY", "SIMILAR", "RATED", "OF_PRODUCT"}


def _enabled() -> bool:
    return bool(getattr(settings, "NEO4J_URI", "")) and GraphDatabase is not None


def _load_props(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _primary_label(labels: str) -> str:
    parts = [p.strip() for p in (labels or "").split("|") if p.strip()]
    for p in parts:
        if p in ALLOWED_LABELS:
            return p
    return parts[0] if parts else ""


def _node_params(row: dict[str, str]) -> tuple[str, dict[str, Any]]:
    label = _primary_label(row.get("labels", ""))
    props = _load_props(row.get("props", ""))
    if label == "User":
        return label, {"id": props.get("id") or row.get("node_key", "").split(":", 1)[-1]}
    if label == "Product":
        return label, {"id": props.get("id") or row.get("node_key", "").split(":", 1)[-1]}
    if label == "Category":
        return label, {"id": props.get("id") or row.get("node_key", "").split(":", 1)[-1]}
    if label == "Query":
        return label, {"text": props.get("text") or row.get("node_key", "").split(":", 1)[-1]}
    if label == "ProductRating":
        return label, {"key": props.get("key") or row.get("node_key", "").split(":", 1)[-1]}
    return label, {}


def _node_params_from_key_and_props(label: str, key: str, raw_props: str) -> tuple[str, dict[str, Any]]:
    props = _load_props(raw_props)
    if label == "User":
        return label, {"id": props.get("id") or key}
    if label == "Product":
        return label, {"id": props.get("id") or key}
    if label == "Category":
        return label, {"id": props.get("id") or key}
    if label == "Query":
        return label, {"text": props.get("text") or key}
    if label == "ProductRating":
        return label, {"key": props.get("key") or key}
    return label, {}


def _merge_node(session, label: str, props: dict[str, Any], extra_props: dict[str, Any]) -> None:
    if label == "User":
        session.run(
            """
            MERGE (n:User {id: $id})
            SET n += $props
            """,
            id=str(props["id"]),
            props=extra_props,
        )
    elif label == "Product":
        session.run(
            """
            MERGE (n:Product {id: $id})
            SET n += $props
            """,
            id=int(props["id"]),
            props=extra_props,
        )
    elif label == "Category":
        session.run(
            """
            MERGE (n:Category {id: $id})
            SET n += $props
            """,
            id=int(props["id"]),
            props=extra_props,
        )
    elif label == "Query":
        session.run(
            """
            MERGE (n:Query {text: $text})
            SET n += $props
            """,
            text=str(props["text"]),
            props=extra_props,
        )
    elif label == "ProductRating":
        session.run(
            """
            MERGE (n:ProductRating {key: $key})
            SET n += $props
            """,
            key=str(props["key"]),
            props=extra_props,
        )


def _match_clause(prefix: str, label: str, props: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if label == "User":
        return f"({prefix}:User {{id: ${prefix}_id}})", {f"{prefix}_id": str(props["id"])}
    if label == "Product":
        return f"({prefix}:Product {{id: ${prefix}_id}})", {f"{prefix}_id": int(props["id"])}
    if label == "Category":
        return f"({prefix}:Category {{id: ${prefix}_id}})", {f"{prefix}_id": int(props["id"])}
    if label == "Query":
        return f"({prefix}:Query {{text: ${prefix}_text}})", {f"{prefix}_text": str(props["text"])}
    if label == "ProductRating":
        return f"({prefix}:ProductRating {{key: ${prefix}_key}})", {f"{prefix}_key": str(props["key"])}
    raise ValueError(f"Unsupported label: {label}")


class Command(BaseCommand):
    help = "Import a KB graph snapshot CSV back into Neo4j."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, default=str(Path("/app/reports/kb_graph_snapshot.csv")))

    def handle(self, *args, **opts):
        if not _enabled():
            raise SystemExit("Neo4j is not configured (NEO4J_URI missing or neo4j driver not installed).")

        path = Path(str(opts["file"]))
        if not path.exists():
            raise SystemExit(f"Snapshot file not found: {path}")

        with path.open("r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        node_rows = [r for r in rows if (r.get("row_type") or "").upper() == "NODE"]
        edge_rows = [r for r in rows if (r.get("row_type") or "").upper() == "EDGE"]

        driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
        try:
            with driver.session() as session:
                for row in node_rows:
                    label, props = _node_params(row)
                    if not label or label not in ALLOWED_LABELS:
                        continue
                    extra_props = _load_props(row.get("props", ""))
                    _merge_node(session, label, props, extra_props)

                for row in edge_rows:
                    rel_type = str(row.get("rel_type") or "").strip()
                    if rel_type not in ALLOWED_REL_TYPES:
                        continue

                    src_label = _primary_label(row.get("source_labels", ""))
                    dst_label = _primary_label(row.get("target_labels", ""))
                    _, src_props = _node_params_from_key_and_props(src_label, row.get("source_key", ""), row.get("source_props", ""))
                    _, dst_props = _node_params_from_key_and_props(dst_label, row.get("target_key", ""), row.get("target_props", ""))

                    src_clause, src_params = _match_clause("a", src_label, src_props)
                    dst_clause, dst_params = _match_clause("b", dst_label, dst_props)
                    params = {**src_params, **dst_params, "props": _load_props(row.get("props", ""))}
                    session.run(
                        f"""
                        MATCH {src_clause}, {dst_clause}
                        MERGE (a)-[r:{rel_type}]->(b)
                        SET r += $props
                        """,
                        **params,
                    )
        finally:
            driver.close()

        self.stdout.write(self.style.SUCCESS(f"Imported snapshot from: {path}"))
        self.stdout.write(self.style.SUCCESS(f"Nodes: {len(node_rows)}, edges: {len(edge_rows)}"))
