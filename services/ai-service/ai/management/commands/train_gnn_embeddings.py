from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db import transaction

from ...application.interaction_gateway import list_recent_events
from ...infrastructure.models import GnnProductEmbedding, GnnUserEmbedding
from ...research.lightgcn import Interaction, build_index_map, build_index_map_int, train_lightgcn_bpr


@dataclass(frozen=True)
class Edge:
    user_id: str
    product_id: int
    weight: float


_W = {"view": 1.0, "click": 2.0, "add_to_cart": 5.0, "purchase": 10.0}


class Command(BaseCommand):
    help = "Train Phase-4 LightGCN embeddings from behavior events and store them in pgvector tables."

    def add_arguments(self, parser):
        parser.add_argument("--dim", type=int, default=64)
        parser.add_argument("--layers", type=int, default=2)
        parser.add_argument("--epochs", type=int, default=5)
        parser.add_argument("--lr", type=float, default=0.01)
        parser.add_argument("--reg", type=float, default=1e-4)
        parser.add_argument("--limit-events", type=int, default=8000)
        parser.add_argument("--min-user-events", type=int, default=2)

    def handle(self, *args, **opts):
        dim = int(opts["dim"])
        layers = int(opts["layers"])
        epochs = int(opts["epochs"])
        lr = float(opts["lr"])
        reg = float(opts["reg"])
        limit_events = int(opts["limit_events"])
        min_user_events = int(opts["min_user_events"])

        events = list_recent_events(limit=limit_events)
        edges: list[Edge] = []
        for e in sorted(events, key=lambda x: x.created_at):
            if e.product_id is None:
                continue
            if e.event_type not in _W:
                continue
            edges.append(Edge(user_id=str(e.user_id), product_id=int(e.product_id), weight=float(_W[e.event_type])))

        by_user: dict[str, list[Edge]] = defaultdict(list)
        for ed in edges:
            by_user[ed.user_id].append(ed)
        by_user = {u: xs for u, xs in by_user.items() if len(xs) >= min_user_events}
        if not by_user:
            self.stdout.write(self.style.WARNING("Not enough events to train LightGCN embeddings."))
            return

        users = list(by_user.keys())
        items = sorted({e.product_id for xs in by_user.values() for e in xs})

        u_map = build_index_map(users)
        i_map = build_index_map_int(items)

        interactions: list[Interaction] = []
        for u, xs in by_user.items():
            uid = u_map[u]
            # collapse duplicates: sum weights per product
            acc: dict[int, float] = defaultdict(float)
            for ed in xs:
                acc[ed.product_id] += float(ed.weight)
            for pid, w in acc.items():
                if pid not in i_map:
                    continue
                interactions.append(Interaction(user_id=str(uid), product_id=i_map[pid], weight=float(w)))

        self.stdout.write(
            f"Training LightGCN: users={len(u_map)} items={len(i_map)} interactions={len(interactions)} "
            f"dim={dim} layers={layers} epochs={epochs}"
        )

        u_vecs, i_vecs = train_lightgcn_bpr(
            interactions=interactions,
            num_users=len(u_map),
            num_items=len(i_map),
            dim=dim,
            layers=layers,
            epochs=epochs,
            lr=lr,
            reg=reg,
        )

        idx_to_user = {idx: uid for uid, idx in u_map.items()}
        idx_to_item = {idx: pid for pid, idx in i_map.items()}

        with transaction.atomic():
            GnnProductEmbedding.objects.all().delete()
            GnnUserEmbedding.objects.all().delete()

            GnnProductEmbedding.objects.bulk_create(
                [GnnProductEmbedding(product_id=int(idx_to_item[i]), embedding=i_vecs[i]) for i in range(len(i_vecs))],
                batch_size=500,
            )
            GnnUserEmbedding.objects.bulk_create(
                [GnnUserEmbedding(user_id=str(idx_to_user[i]), embedding=u_vecs[i]) for i in range(len(u_vecs))],
                batch_size=500,
            )

        self.stdout.write(
            self.style.SUCCESS(f"Saved {len(i_vecs)} GNN product embeddings and {len(u_vecs)} GNN user embeddings.")
        )

