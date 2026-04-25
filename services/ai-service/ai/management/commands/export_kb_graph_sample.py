from __future__ import annotations

import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings

try:
    from neo4j import GraphDatabase
except Exception:  # noqa: BLE001
    GraphDatabase = None  # type: ignore[assignment]


SAMPLE_EDGES_CYPHER = """
// 20 dòng edges (để copy vào báo cáo)
MATCH (u:User)-[r]->(n)
RETURN
  u.id AS user_id,
  type(r) AS rel_type,
  coalesce(n.id, n.text) AS target_id,
  labels(n) AS target_labels,
  coalesce(r.w, 1.0) AS weight
ORDER BY weight DESC
LIMIT $limit;
"""


COMPLEX_GRAPH_CYPHER = """
// Query để vẽ graph "đẹp/phức tạp" trong Neo4j Browser (chạy rồi chụp ảnh)
// Mục tiêu: 1 user + hàng xóm (co-occurrence) + products + categories + queries
MATCH (me:User {id: $user_id})
OPTIONAL MATCH (me)-[:SEARCHED]->(q:Query)
WITH me, collect(DISTINCT q)[0..8] AS qs
OPTIONAL MATCH (me)-[r1]->(p:Product)<-[r2]-(other:User)-[r3]->(rec:Product)
WITH me, qs, p, other, rec, r1, r2, r3
LIMIT 200
OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c1:Category)
OPTIONAL MATCH (rec)-[:IN_CATEGORY]->(c2:Category)
RETURN me, qs, p, other, rec, c1, c2, r1, r2, r3;
"""


class Command(BaseCommand):
    help = "Export 20 sample KB_Graph edges to CSV and generate Cypher for Neo4j Browser screenshots."

    def add_arguments(self, parser):
        parser.add_argument("--out-dir", type=str, default=str(Path("/app/reports")))
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--user-id", type=str, default="user-0001")

    def handle(self, *args, **opts):
        if not settings.NEO4J_URI or GraphDatabase is None:
            raise SystemExit("Neo4j is not configured (NEO4J_URI missing or neo4j driver not installed).")

        out_dir = Path(str(opts["out_dir"]))
        out_dir.mkdir(parents=True, exist_ok=True)
        limit = max(1, min(200, int(opts["limit"])))
        user_id = str(opts["user_id"])

        driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
        try:
            with driver.session() as session:
                rows = list(session.run(SAMPLE_EDGES_CYPHER, limit=limit))
        finally:
            driver.close()

        out_csv = out_dir / "kb_graph_sample_20_edges.csv"
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["user_id", "rel_type", "target_id", "target_labels", "weight"])
            for r in rows:
                w.writerow(
                    [
                        r.get("user_id"),
                        r.get("rel_type"),
                        r.get("target_id"),
                        "|".join(list(r.get("target_labels") or [])),
                        r.get("weight"),
                    ]
                )

        out_cypher = out_dir / "kb_graph_visualize.cypher"
        out_cypher.write_text(
            f"// Use in Neo4j Browser, then take a screenshot.\n:param user_id => '{user_id}';\n\n{COMPLEX_GRAPH_CYPHER}\n",
            encoding="utf-8",
        )

        self.stdout.write(self.style.SUCCESS(f"Wrote sample edges CSV: {out_csv}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote visualization Cypher: {out_cypher}"))

