from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from app.domain.models import CyclicTaskReport


class Command(BaseCommand):
    help = "Show the latest stored reports for cyclic background tasks."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--task", dest="task_name", help="Filter by a single task name.")
        parser.add_argument("--limit", type=int, default=3, help="Maximum reports to print per query.")

    def handle(self, *args, **options) -> None:
        task_name: str | None = options.get("task_name")
        limit = max(int(options["limit"]), 1)

        queryset = CyclicTaskReport.objects.all().order_by("-started_at", "-id")
        if task_name:
            queryset = queryset.filter(task_name=task_name)

        reports = list(queryset[:limit])
        if not reports:
            self.stdout.write(self.style.WARNING("No cyclic task reports found."))
            return

        for report in reports:
            self.stdout.write(
                f"{report.task_name} | {report.status} | "
                f"started={report.started_at.isoformat()} | "
                f"finished={report.finished_at.isoformat()} | "
                f"duration_ms={report.duration_ms}"
            )
            self.stdout.write(json.dumps(report.payload, ensure_ascii=False, indent=2, default=str))