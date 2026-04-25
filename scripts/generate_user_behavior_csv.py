from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class Row:
    user_id: str
    product_id: int | None
    action: str
    timestamp: str


BEHAVIORS_8 = [
    "view",
    "click",
    "add_to_cart",
    "purchase",
    "search",
    "browse_products",
    "browse_recommended",
    "checkout",
]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def generate_rows(
    *,
    users: int,
    product_max_id: int,
    seed: int,
    events_min: int,
    events_max: int,
) -> list[Row]:
    rnd = random.Random(seed)
    base = datetime(2026, 4, 1, 8, 0, 0, tzinfo=timezone.utc)

    # Note: queries are intentionally not stored in this CSV since the assignment image shows only 4 fields.
    # We keep them here to guide the synthetic session flow (search-like behavior).
    queries = [
        "laptop học lập trình",
        "điện thoại chụp ảnh đẹp",
        "tai nghe chống ồn",
        "cáp sạc type-c",
        "củ sạc nhanh 65w",
        "iphone 15 ốp lưng",
        "gaming laptop rtx",
        "smartphone dưới 7 triệu",
    ]

    rows: list[Row] = []
    for u in range(users):
        user_id = f"user-{u+1:04d}"

        dt = base + timedelta(minutes=rnd.randint(0, 60 * 24 * 10))
        dt += timedelta(seconds=rnd.randint(0, 59))

        # Track products seen/carted to keep sequences realistic.
        seen_product_ids: list[int] = []
        carted_product_ids: list[int] = []

        def add(action: str, pid: int | None):
            nonlocal dt
            rows.append(Row(user_id=user_id, product_id=pid, action=action, timestamp=_iso(dt)))
            dt += timedelta(seconds=rnd.randint(5, 90))

        # A small set of minimum counts per user to reduce class-imbalance.
        min_counts = {
            "browse_products": 2,
            "search": 2,
            "browse_recommended": 2,
            "view": 6,
            "click": 3,
            "add_to_cart": 2,
            "checkout": 2,
            "purchase": 1,
        }
        counts: dict[str, int] = {k: 0 for k in BEHAVIORS_8}

        def pick_product_for(action: str) -> int | None:
            if action in {"view", "click"}:
                pid = rnd.randint(1, product_max_id)
                seen_product_ids.append(pid)
                return pid
            if action == "add_to_cart":
                pid = rnd.choice(seen_product_ids) if seen_product_ids else rnd.randint(1, product_max_id)
                carted_product_ids.append(pid)
                return pid
            if action == "purchase":
                if carted_product_ids:
                    return rnd.choice(carted_product_ids)
                if seen_product_ids:
                    return rnd.choice(seen_product_ids)
                return rnd.randint(1, product_max_id)
            return None

        def add_counted(action: str) -> None:
            pid = pick_product_for(action)
            add(action, pid)
            counts[action] = counts.get(action, 0) + 1

        # Generate a session-like sequence with a simple state machine (more learnable than pure random).
        # Transitions favor realistic e-commerce funnels:
        # browse/search -> view -> click -> add_to_cart -> checkout -> purchase
        def next_action(prev: str | None) -> str:
            if prev is None:
                return rnd.choice(["browse_products", "search"])
            r = rnd.random()
            if prev in {"browse_products", "browse_recommended", "search"}:
                return "view" if r < 0.8 else ("browse_products" if r < 0.9 else "browse_recommended")
            if prev == "view":
                if r < 0.55:
                    return "click"
                if r < 0.70:
                    return "view"
                if r < 0.88:
                    return "add_to_cart"
                return "search"
            if prev == "click":
                if r < 0.55:
                    return "view"
                if r < 0.78:
                    return "add_to_cart"
                if r < 0.90:
                    return "browse_recommended"
                return "search"
            if prev == "add_to_cart":
                if r < 0.55:
                    return "checkout"
                if r < 0.75:
                    return "view"
                if r < 0.90:
                    return "click"
                return "search"
            if prev == "checkout":
                if r < 0.70:
                    return "purchase"
                if r < 0.85:
                    return "add_to_cart"
                return "browse_recommended"
            if prev == "purchase":
                return rnd.choice(["browse_recommended", "browse_products", "search"])
            return rnd.choice(BEHAVIORS_8)

        # Determine target length (increase slightly to provide more supervised samples).
        n_total = rnd.randint(max(30, events_min), max(60, events_max))

        prev: str | None = None
        # Seed with a short funnel prefix.
        for a in ["browse_products", "search", "view", "click", "add_to_cart", "checkout"]:
            add_counted(a)
            prev = a
        # Optionally purchase once early.
        if rnd.random() < 0.75:
            add_counted("purchase")
            prev = "purchase"
        _ = rnd.choice(queries)

        while sum(counts.values()) < n_total:
            a = next_action(prev)
            add_counted(a)
            prev = a

        # Ensure minimum counts for each action (top up at the end).
        for a, m in min_counts.items():
            while counts.get(a, 0) < m:
                add_counted(a)

    return rows


def write_csv(path: Path, rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "product_id", "action", "timestamp"])
        for r in rows:
            w.writerow([r.user_id, "" if r.product_id is None else int(r.product_id), r.action, r.timestamp])


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate synthetic user behavior CSV for SAD assignment.")
    ap.add_argument("--out", type=str, default=str(Path("data") / "data_user500.csv"))
    ap.add_argument("--users", type=int, default=500)
    ap.add_argument("--product-max-id", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--events-min", type=int, default=20)
    ap.add_argument("--events-max", type=int, default=45)
    args = ap.parse_args()

    rows = generate_rows(
        users=max(1, int(args.users)),
        product_max_id=max(1, int(args.product_max_id)),
        seed=int(args.seed),
        events_min=max(8, int(args.events_min)),
        events_max=max(8, int(args.events_max)),
    )
    write_csv(Path(args.out), rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

