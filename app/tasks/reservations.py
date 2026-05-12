"""Scheduled ARQ job for automatic reservation status management."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import close_old_connections
from django.utils import timezone
from asgiref.sync import sync_to_async

from app.domain.models import CyclicTaskReport, LibraryAdmin, MailNotification, Reservation, Status

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


async def _bulk_buffer_notifications(
    items: list[tuple[int, int, int]],
    new_status: str,
) -> None:
    """Bulk-create MailNotification rows for readers and library admins.

    ``items`` is a list of (reservation_id, reader_id, library_id) tuples
    collected *before* the bulk status update.
    """
    if not items:
        return

    # One notification per reader.
    await MailNotification.objects.abulk_create([
        MailNotification(user_id=reader_id, reservation_id=res_id, new_status=new_status)
        for res_id, reader_id, _ in items
    ])

    # One notification per library admin for each affected reservation.
    lib_ids = {lib_id for _, _, lib_id in items}
    lib_to_res_ids: dict[int, list[int]] = {}
    for res_id, _, lib_id in items:
        lib_to_res_ids.setdefault(lib_id, []).append(res_id)

    admin_notifs: list[MailNotification] = []
    async for admin_user_id, admin_lib_id in LibraryAdmin.objects.filter(
        library_id__in=lib_ids
    ).values_list("user_id", "library_id"):
        for res_id in lib_to_res_ids.get(admin_lib_id, []):
            admin_notifs.append(
                MailNotification(user_id=admin_user_id, reservation_id=res_id, new_status=new_status)
            )
    if admin_notifs:
        await MailNotification.objects.abulk_create(admin_notifs)


async def _reservation_manager_impl() -> dict[str, Any]:
    now = timezone.now()
    expired_threshold = now - timedelta(hours=PENDING_EXPIRY_HOURS)
    closed_threshold = now - timedelta(days=ACCEPTED_CLOSE_DAYS)

    expired_status, _ = await Status.objects.aget_or_create(name="expired")
    closed_status, _ = await Status.objects.aget_or_create(name="closed")

    # Collect affected IDs before each bulk update so we can notify afterwards.
    pending_to_expire = [
        (res_id, reader_id, lib_id)
        async for res_id, reader_id, lib_id in Reservation.objects.filter(
            status__name="pending",
            updated_at__lte=expired_threshold,
        ).values_list("id", "reader_id", "library_id")
    ]
    if pending_to_expire:
        expired_count = await Reservation.objects.filter(
            id__in=[item[0] for item in pending_to_expire]
        ).aupdate(status_id=expired_status.id, updated_at=now, end_time=now)
        await _bulk_buffer_notifications(pending_to_expire, "expired")
    else:
        expired_count = 0

    accepted_to_close = [
        (res_id, reader_id, lib_id)
        async for res_id, reader_id, lib_id in Reservation.objects.filter(
            status__name="accepted",
            updated_at__lte=closed_threshold,
        ).values_list("id", "reader_id", "library_id")
    ]
    if accepted_to_close:
        closed_count = await Reservation.objects.filter(
            id__in=[item[0] for item in accepted_to_close]
        ).aupdate(status_id=closed_status.id, updated_at=now, end_time=now)
        await _bulk_buffer_notifications(accepted_to_close, "closed")
    else:
        closed_count = 0

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
