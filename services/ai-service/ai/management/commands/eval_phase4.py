from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from ...research.eval_phase4 import eval_recsys, write_json


class Command(BaseCommand):
    help = "Run Phase-4 offline evaluation and export report artifacts into /app/reports."

    def add_arguments(self, parser):
        parser.add_argument("--out-dir", type=str, default=str(Path("/app/reports")))
        parser.add_argument("--limit-users", type=int, default=200)
        parser.add_argument("--limit-events", type=int, default=12000)
        parser.add_argument("--k", type=str, default="5,10")

    def handle(self, *args, **opts):
        out_dir = Path(str(opts["out_dir"]))
        out_dir.mkdir(parents=True, exist_ok=True)
        limit_users = int(opts["limit_users"])
        _limit_events = int(opts["limit_events"])  # reserved for future; kept for report repeatability
        ks = []
        for part in str(opts["k"]).split(","):
            s = part.strip()
            if not s:
                continue
            try:
                ks.append(int(s))
            except Exception:  # noqa: BLE001
                continue
        ks = sorted({k for k in ks if 1 <= k <= 50}) or [5, 10]

        res = eval_recsys(k_list=ks, limit_users=limit_users)
        out_path = out_dir / "phase4_recsys_metrics.json"
        write_json(str(out_path), res)
        self.stdout.write(self.style.SUCCESS(f"Wrote {out_path}"))

