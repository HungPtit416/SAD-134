from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from ...application.graph_gateway import backfill_product_categories_to_graph, upsert_event_to_graph
from ...application.interaction_gateway import list_events_since
from ...application.product_gateway import list_products
from ...infrastructure.models import GraphSyncState


class Command(BaseCommand):
    help = "Incrementally sync interaction-service events into the Neo4j graph."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--skip-catalog-categories", action="store_true", help="Skip MERGE of all product/category nodes from catalog.")

    def handle(self, *args, **opts):
        batch_size = max(1, min(2000, int(opts["batch_size"])))
        skip_cat = bool(opts["skip_catalog_categories"])

        total = 0
        while True:
            state, _ = GraphSyncState.objects.get_or_create(key="default", defaults={"last_event_id": 0})
            since = int(state.last_event_id)
            batch = list_events_since(since, limit=batch_size)
            if not batch:
                break

            products = list_products()
            by_id = {p.id: p for p in products}

            max_id = since
            for ev in batch:
                p = by_id.get(ev.product_id) if ev.product_id is not None else None
                upsert_event_to_graph(
                    user_id=ev.user_id,
                    event_type=ev.event_type,
                    product_id=ev.product_id,
                    query=ev.query,
                    metadata=ev.metadata,
                    category_id=p.category_id if p else None,
                    category_name=p.category_name if p else None,
                )
                max_id = max(max_id, ev.id)

            if max_id <= since and batch:
                self.stdout.write(
                    self.style.ERROR(
                        "Cursor did not advance (interaction-service may be missing since_id support). "
                        "Rebuild interaction-service and retry."
                    )
                )
                break

            with transaction.atomic():
                GraphSyncState.objects.filter(pk=state.pk).update(last_event_id=max_id)

            total += len(batch)
            self.stdout.write(self.style.SUCCESS(f"Synced {len(batch)} event(s); last_event_id={max_id}"))

            if len(batch) < batch_size:
                break

        if not skip_cat:
            tuples = [(p.id, p.category_id, p.category_name) for p in list_products()]
            backfill_product_categories_to_graph(tuples)
            self.stdout.write(self.style.SUCCESS(f"Catalog category nodes refreshed ({len(tuples)} products)."))

        self.stdout.write(self.style.SUCCESS(f"Done. Total events processed this run: {total}"))
