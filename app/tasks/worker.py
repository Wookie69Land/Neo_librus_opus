"""ARQ worker configuration for scheduled Librarius jobs."""
from __future__ import annotations

import os

import django
from arq.connections import RedisSettings
from arq.cron import cron

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "app.core.settings.production"))
django.setup()

from app.core.settings.base import env
from app.tasks.ai import run_ai_recommendation_pipeline
from app.tasks.books import (
    assign_books_to_random_libraries,
    book_enricher,
    cyclic_book_manager,
    cyclic_book_seeder,
)
from app.tasks.mailing import mailing_manager
from app.tasks.reservations import reservation_manager


async def startup(ctx: dict) -> None:
    """Populate worker context with reusable settings."""

    ctx["google_books_api_key"] = env("GOOGLE_BOOKS_API_KEY", default="") or None
    ctx["google_books_timeout"] = env.float("GOOGLE_BOOKS_TIMEOUT", default=15.0)


class WorkerSettings:
    """ARQ worker settings and cron schedule."""

    keep_result = 3600  # keep job results in Redis for 1 hour
    functions = [
        cyclic_book_seeder,
        cyclic_book_manager,
        book_enricher,
        assign_books_to_random_libraries,
        run_ai_recommendation_pipeline,
        reservation_manager,
        mailing_manager,
    ]
    on_startup = startup
    redis_settings = RedisSettings(
        host=env("REDIS_HOST", default="redis"),
        port=env.int("REDIS_PORT", default=6379),
        database=env.int("REDIS_DATABASE", default=0),
    )
    cron_jobs = [
        cron(cyclic_book_seeder, name="cyclic_book_seeder", hour={7, 19}, minute=0),
        cron(cyclic_book_manager, name="cyclic_book_manager", hour={7, 19}, minute=15),
        cron(reservation_manager, name="reservation_manager", second=0),
        cron(
            mailing_manager,
            name="mailing_manager",
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
            second=0,
        ),
    ]
