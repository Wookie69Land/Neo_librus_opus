from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Awaitable

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app.tasks.books import (
    assign_books_to_random_libraries,
    book_enricher,
    cyclic_book_manager,
    cyclic_book_seeder,
)

TaskCallable = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

TASKS: dict[str, TaskCallable] = {
    "assign_books_to_random_libraries": assign_books_to_random_libraries,
    "book_enricher": book_enricher,
    "cyclic_book_manager": cyclic_book_manager,
    "cyclic_book_seeder": cyclic_book_seeder,
}


class Command(BaseCommand):
    help = "Run a cyclic ARQ task immediately for smoke testing or manual maintenance."

    def add_arguments(self, parser) -> None:
        parser.add_argument("task_name", choices=sorted(TASKS))

    def handle(self, *args, **options) -> None:
        task_name: str = options["task_name"]
        task = TASKS[task_name]
        ctx = {
            "google_books_api_key": settings.GOOGLE_BOOKS_API_KEY or None,
            "google_books_timeout": settings.GOOGLE_BOOKS_TIMEOUT,
        }

        self.stdout.write(f"Running task: {task_name}")

        try:
            result = asyncio.run(task(ctx))
        except Exception as exc:
            raise CommandError(f"Task '{task_name}' failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Task finished successfully."))
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))