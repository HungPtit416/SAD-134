import os
import random
import time
from typing import Any

import requests

from .models import StockItem


def seed() -> None:
    product_base = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:8001").rstrip("/")
    url = f"{product_base}/api/products/"
    last_err: Exception | None = None
    for attempt in range(15):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            break
        except (requests.exceptions.RequestException, OSError) as e:
            last_err = e
            time.sleep(2)
    else:
        raise RuntimeError(f"seed: product-service not reachable at {url}") from last_err
    data: Any = resp.json()
    products = data if isinstance(data, list) else data.get("results", [])

    rng = random.Random(20260413)
    for p in products:
        pid = int(p["id"])
        # Make stock look like retail: 10..30
        initial = int(rng.randint(10, 30))
        item, created = StockItem.objects.get_or_create(
            product_id=pid,
            defaults={"initial_quantity": initial, "quantity": initial},
        )
        if created:
            continue
        # Keep initial_quantity stable once set
        if item.initial_quantity <= 0:
            item.initial_quantity = initial
            if item.quantity <= 0:
                item.quantity = initial
            item.save(update_fields=["initial_quantity", "quantity"])

