from __future__ import annotations

import random
import time

from django.core.management.base import BaseCommand

from ...infrastructure.models import Event


class Command(BaseCommand):
    help = "Seed synthetic user behavior events for demo/training."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=50)
        parser.add_argument("--sessions-per-user", type=int, default=3)
        parser.add_argument("--events-per-session", type=int, default=30)
        parser.add_argument("--product-max-id", type=int, default=30)
        parser.add_argument("--purchase-rate", type=float, default=0.05)
        parser.add_argument("--cart-rate", type=float, default=0.15)
        parser.add_argument("--view-rate", type=float, default=0.7)

    def handle(self, *args, **opts):
        users = max(1, int(opts["users"]))
        sessions_per_user = max(1, int(opts["sessions_per_user"]))
        events_per_session = max(1, int(opts["events_per_session"]))
        product_max_id = max(1, int(opts["product_max_id"]))

        purchase_rate = float(opts["purchase_rate"])
        cart_rate = float(opts["cart_rate"])
        view_rate = float(opts["view_rate"])

        queries = [
            "cheap phone",
            "gaming laptop",
            "wireless earbuds",
            "fast charger",
            "usb c cable",
            "iphone case",
            "android phone",
            "budget laptop",
        ]

        created = 0
        rnd = random.Random(42)

        for u in range(users):
            user_id = f"seed-user-{u+1:03d}"
            for s in range(sessions_per_user):
                session_id = f"{user_id}-s{s+1}-{int(time.time())}"

                # Start with a search
                q = rnd.choice(queries)
                Event.objects.create(
                    user_id=user_id,
                    session_id=session_id,
                    event_type="search",
                    query=q,
                    metadata={"seed": True},
                )
                created += 1

                last_viewed: list[int] = []
                for _ in range(events_per_session):
                    r = rnd.random()
                    pid = rnd.randint(1, product_max_id)

                    if r < purchase_rate and last_viewed:
                        pid = rnd.choice(last_viewed)
                        Event.objects.create(
                            user_id=user_id,
                            session_id=session_id,
                            event_type="purchase",
                            product_id=pid,
                            metadata={"seed": True, "quantity": 1},
                        )
                        created += 1
                        continue

                    if r < purchase_rate + cart_rate and last_viewed:
                        pid = rnd.choice(last_viewed)
                        Event.objects.create(
                            user_id=user_id,
                            session_id=session_id,
                            event_type="add_to_cart",
                            product_id=pid,
                            metadata={"seed": True, "quantity": 1},
                        )
                        created += 1
                        continue

                    if r < purchase_rate + cart_rate + view_rate:
                        Event.objects.create(
                            user_id=user_id,
                            session_id=session_id,
                            event_type="view",
                            product_id=pid,
                            metadata={"seed": True},
                        )
                        last_viewed.append(pid)
                        last_viewed = last_viewed[-20:]
                        created += 1
                        continue

                    # occasionally: update qty/remove
                    Event.objects.create(
                        user_id=user_id,
                        session_id=session_id,
                        event_type="update_cart_qty",
                        product_id=pid,
                        metadata={"seed": True, "quantity": rnd.randint(1, 3)},
                    )
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded {created} events."))

