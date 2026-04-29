"""Scheduled ARQ job for automatic reservation status management."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import close_old_connections
from django.utils import timezone
from asgiref.sync import sync_to_async

from app.domain.models import CyclicTaskReport, Reservation, Status

PENDING_EXPIRY_HOURS = 48
ACCEPTED_CLOSE_DAYS = 3


async def _refresh_db_connections() -> None:
    await sync_to_async(close_old_connections, thread_sensitive=True)()


async def _prune_old_reports(task_name: str, retention: int) -> None:
    report_ids_to_delete: list[int] = []
    retained = 0
    async for report_id in CyclicTaskReport.objects.filter(task_name=task_name).order_by(
        "-started_at", "-id"
    ).values_list("id", flat=True):
        retained += 1
        if retained > retention:
            report_ids_to_delete.append(report_id)
    if report_ids_to_delete:
        await CyclicTaskReport.objects.filter(id__in=report_ids_to_delete).adelete()


async def _reservation_manager_impl() -> dict[str, Any]:
    now = timezone.now()
    expired_threshold = now - timedelta(hours=PENDING_EXPIRY_HOURS)
    closed_threshold = now - timedelta(days=ACCEPTED_CLOSE_DAYS)

    expired_status, _ = await Status.objects.aget_or_create(name="expired")
    closed_status, _ = await Status.objects.aget_or_create(name="closed")

    # pending reservations with no admin action after 48 h → expired
    expired_count = await Reservation.objects.filter(
        status__name="pending",
        updated_at__lte=expired_threshold,
    ).aupdate(status_id=expired_status.id, updated_at=now)

    # accepted reservations not picked up within 3 days → closed
    closed_count = await Reservation.objects.filter(
        status__name="accepted",
        updated_at__lte=closed_threshold,
    ).aupdate(status_id=closed_status.id, updated_at=now)

    return {
        "status": "completed",
        "expired": expired_count,
        "closed": closed_count,
    }


async def reservation_manager(ctx: dict) -> dict[str, Any]:
    """ARQ entry-point: expire stale pending reservations and close accepted ones."""
    from django.conf import settings

    await _refresh_db_connections()
    task_name = "reservation_manager"
    started_at = timezone.now()

    try:
        result = await _reservation_manager_impl()
    except Exception as exc:
        finished_at = timezone.now()
        duration_ms = max(int((finished_at - started_at).total_seconds() * 1000), 0)
        await CyclicTaskReport.objects.acreate(
            task_name=task_name,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            payload={"error": str(exc), "error_type": type(exc).__name__},
        )
        await _refresh_db_connections()
        raise

    finished_at = timezone.now()
    duration_ms = max(int((finished_at - started_at).total_seconds() * 1000), 0)
    retention = max(getattr(settings, "CYCLIC_TASK_REPORT_RETENTION", 3), 1)
    await CyclicTaskReport.objects.acreate(
        task_name=task_name,
        status=result.get("status", "completed"),
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        payload=result,
    )
    await _prune_old_reports(task_name, retention)
    await _refresh_db_connections()
    return result
