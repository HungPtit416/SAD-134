from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from ...infrastructure.models import Event


@dataclass(frozen=True)
class CsvRow:
    user_id: str
    product_id: int | None
    action: str
    timestamp: datetime | None


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    dt = parse_datetime(s)
    if dt is not None:
        return dt
    # Best-effort: allow "YYYY-mm-dd HH:MM:SS"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


class Command(BaseCommand):
    help = "Import synthetic behavior CSV (user_id, product_id, action, timestamp) into interaction-service Event table."

    def add_arguments(self, parser):
        parser.add_argument("--path", type=str, default=str(Path("/app/data/data_user500.csv")))
        parser.add_argument("--default-session", type=str, default="csv-import")
        parser.add_argument("--metadata-seed", action="store_true", help="Add metadata.seed=true to imported rows.")
        parser.add_argument("--truncate", action="store_true", help="Delete existing events before importing.")
        parser.add_argument("--limit", type=int, default=0, help="Import only first N rows (0 = all).")
        parser.add_argument("--batch-size", type=int, default=2000)

    def handle(self, *args, **opts):
        path = Path(str(opts["path"]))
        if not path.exists():
            raise SystemExit(f"CSV not found: {path}")

        batch_size = max(100, min(10_000, int(opts["batch_size"])))
        default_session = str(opts["default_session"] or "csv-import")[:64]
        add_seed = bool(opts["metadata_seed"])
        truncate = bool(opts["truncate"])
        limit = int(opts["limit"] or 0)

        if truncate:
            Event.objects.all().delete()
            self.stdout.write(self.style.WARNING("Deleted all existing events (truncate enabled)."))

        created = 0
        buf: list[Event] = []

        def flush():
            nonlocal created, buf
            if not buf:
                return
            with transaction.atomic():
                Event.objects.bulk_create(buf, batch_size=batch_size)
            created += len(buf)
            buf = []

        with path.open("r", newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            expected = {"user_id", "product_id", "action", "timestamp"}
            if not expected.issubset(set(r.fieldnames or [])):
                raise SystemExit(f"CSV must contain columns: {sorted(expected)} (got: {r.fieldnames})")

            for i, row in enumerate(r, start=1):
                if limit and (i > limit):
                    break

                user_id = str(row.get("user_id") or "").strip()
                if not user_id:
                    continue

                action = str(row.get("action") or "").strip()
                if not action:
                    continue

                pid_raw = str(row.get("product_id") or "").strip()
                product_id = int(pid_raw) if pid_raw.isdigit() else None

                ts = _parse_ts(str(row.get("timestamp") or "").strip())

                meta = {"source": "csv"} if add_seed else {}
                if add_seed:
                    meta["seed"] = True

                # Map CSV "action" directly to Event.event_type.
                ev = Event(
                    user_id=user_id[:64],
                    session_id=default_session,
                    event_type=action[:64],
                    product_id=product_id,
                    query=None,
                    metadata=meta,
                )
                if ts is not None:
                    ev.created_at = ts  # type: ignore[assignment]

                buf.append(ev)
                if len(buf) >= batch_size:
                    flush()

        flush()
        self.stdout.write(self.style.SUCCESS(f"Imported {created} event(s) from {path}"))

