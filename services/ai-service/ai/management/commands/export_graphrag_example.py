from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from ...application.graphrag import export_graphrag_example


class Command(BaseCommand):
    help = "Export a single GraphRAG evidence JSON file for the final report."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=str, default="user-0001")
        parser.add_argument("--message", type=str, default="Mình cần gợi ý laptop dưới 15 triệu cho học lập trình.")
        parser.add_argument("--out", type=str, default=str(Path("/app/reports/graphrag_example.json")))
        parser.add_argument("--evidence-limit", type=int, default=20)

    def handle(self, *args, **opts):
        user_id = str(opts["user_id"])
        message = str(opts["message"])
        out = str(opts["out"])
        evidence_limit = int(opts["evidence_limit"])

        res = export_graphrag_example(user_id=user_id, message=message, out_path=out, evidence_limit=evidence_limit)
        self.stdout.write(self.style.SUCCESS(f"Wrote: {res['written']} (evidence={res['evidence_count']})"))

