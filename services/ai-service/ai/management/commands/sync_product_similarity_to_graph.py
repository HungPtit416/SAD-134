from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand

from ...application.graph_gateway import upsert_product_similarity_edges
from ...infrastructure.models import DocumentChunk


@dataclass(frozen=True)
class Pair:
    a: int
    b: int
    score: float


class Command(BaseCommand):
    help = "Build (:Product)-[:SIMILAR]->(:Product) edges in Neo4j from pgvector product embeddings."

    def add_arguments(self, parser):
        parser.add_argument("--topk", type=int, default=5, help="How many similar products per product.")
        parser.add_argument("--min-score", type=float, default=0.35, help="Minimum cosine similarity to write an edge.")
        parser.add_argument("--limit-products", type=int, default=0, help="Only process first N products (0 = all).")
        parser.add_argument("--bidirectional", action="store_true", help="Write edges in both directions (A->B and B->A).")

    def handle(self, *args, **opts):
        topk = max(1, min(20, int(opts["topk"])))
        min_score = float(opts["min_score"])
        limit_products = int(opts["limit_products"] or 0)
        bidir = bool(opts["bidirectional"])

        try:
            from pgvector.django import CosineDistance
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"pgvector is required for similarity search: {e}")

        # Ensure pgvector returns distance via annotation so we can store a meaningful similarity score.
        # similarity = clamp(1 - cosine_distance, 0..1)

        qs = DocumentChunk.objects.filter(source_type="product")
        if limit_products > 0:
            qs = qs.order_by("id")[:limit_products]
        rows = list(qs)
        if not rows:
            self.stdout.write(self.style.WARNING("No product DocumentChunk rows found. Run /api/index first."))
            return

        # For each product embedding, find topK nearest neighbors and write SIMILAR edges.
        pairs: list[Pair] = []
        seen = set()

        for ch in rows:
            try:
                pid = int(ch.source_id)
            except Exception:  # noqa: BLE001
                continue

            # Query nearest neighbors in DB using cosine distance.
            nn = (
                DocumentChunk.objects.filter(source_type="product")
                .exclude(source_id=str(pid))
                .annotate(distance=CosineDistance("embedding", ch.embedding))
                .order_by("distance")[: max(1, topk * 3)]
            )
            for n in nn:
                try:
                    nid = int(n.source_id)
                except Exception:  # noqa: BLE001
                    continue

                # Convert cosine distance to similarity (approx): sim = 1 - dist
                # pgvector cosine distance is in [0,2] but in practice embeddings yield [0,1]ish.
                # We clamp to [0,1] for Neo4j storage.
                dist = float(getattr(n, "distance"))
                score = max(0.0, min(1.0, 1.0 - dist))

                if score < min_score:
                    continue

                key = (pid, nid)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(Pair(a=pid, b=nid, score=score))
                if len(pairs) >= 50_000:
                    break
                # Enforce per-product topk
                if len([p for p in pairs if p.a == pid]) >= topk:
                    break

        # If distance wasn't available, score is a placeholder; still good enough to mark SIMILAR links.
        payload: list[tuple[int, int, float]] = [(p.a, p.b, p.score) for p in pairs]
        if bidir:
            payload = payload + [(b, a, sc) for (a, b, sc) in payload]

        written = upsert_product_similarity_edges(pairs=payload, rel_name="SIMILAR")
        self.stdout.write(self.style.SUCCESS(f"Wrote {written} SIMILAR edge(s) to Neo4j (pairs={len(payload)})."))

