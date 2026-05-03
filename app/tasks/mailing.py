"""ARQ job that flushes the MailNotification buffer every 5 minutes.

Architecture
------------
Every reservation status change creates one or more ``MailNotification`` rows
(one for the reader, one per library admin).  This task collects all unsent rows,
groups them by recipient → reservation, composes a single digest email per user,
sends it, and marks the rows as sent.

Failures are per-user: if sending fails for one recipient the rows are left
unsent and retried in the next run.
"""
from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from django.utils import timezone

from app.domain.models import CyclicTaskReport, MailNotification


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


async def _mailing_manager_impl() -> dict[str, Any]:
    from django.conf import settings
    from django.core.mail import send_mail

    now = timezone.now()

    # Collect all unsent notifications with their related objects pre-loaded.
    unsent_qs = (
        MailNotification.objects.filter(sent_at__isnull=True)
        .select_related("user", "reservation__book", "reservation__library")
        .order_by("user_id", "reservation_id", "created_at")
    )

    # Build: { user_id → { "user": ..., "reservations": { res_id → {"reservation": ..., "statuses": [...], "ids": [...]} } } }
    by_user: dict[int, dict[str, Any]] = {}
    async for notif in unsent_qs:
        uid = notif.user_id
        if uid not in by_user:
            by_user[uid] = {"user": notif.user, "reservations": {}}
        rid = notif.reservation_id
        if rid not in by_user[uid]["reservations"]:
            by_user[uid]["reservations"][rid] = {
                "reservation": notif.reservation,
                "statuses": [],
                "ids": [],
            }
        by_user[uid]["reservations"][rid]["statuses"].append(notif.new_status)
        by_user[uid]["reservations"][rid]["ids"].append(notif.id)

    emails_sent = 0
    errors = 0
    sent_ids: list[int] = []

    for data in by_user.values():
        user = data["user"]
        if not user.email:
            continue

        lines: list[str] = [
            f"Hello {user.first_name or user.username},",
            "",
            "Here are your recent reservation updates:",
            "",
        ]
        for res_data in data["reservations"].values():
            res = res_data["reservation"]
            statuses: list[str] = res_data["statuses"]
            lines.append(
                f"Reservation #{res.id} — {res.book.title} at {res.library.name}:"
            )
            for s in statuses:
                lines.append(f"  • status changed to: {s}")
            lines.append("")

        lines += ["", "Best regards,", "Librarius Team"]

        try:
            await sync_to_async(send_mail)(
                subject="Librarius — your reservation updates",
                message="\n".join(lines),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            emails_sent += 1
            for res_data in data["reservations"].values():
                sent_ids.extend(res_data["ids"])
        except Exception:
            errors += 1

    if sent_ids:
        await MailNotification.objects.filter(id__in=sent_ids).aupdate(sent_at=now)

    return {
        "status": "completed",
        "emails_sent": emails_sent,
        "errors": errors,
        "notifications_flushed": len(sent_ids),
    }


async def mailing_manager(ctx: dict) -> dict[str, Any]:
    """ARQ entry-point: flush pending MailNotification buffer every 5 minutes."""
    from django.conf import settings

    await _refresh_db_connections()
    task_name = "mailing_manager"
    started_at = timezone.now()

    try:
        result = await _mailing_manager_impl()
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
        raise

    finished_at = timezone.now()
    duration_ms = max(int((finished_at - started_at).total_seconds() * 1000), 0)
    retention = getattr(settings, "CYCLIC_TASK_REPORT_RETENTION", 3)
    await CyclicTaskReport.objects.acreate(
        task_name=task_name,
        status=result["status"],
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        payload=result,
    )
    await _prune_old_reports(task_name, retention)
    return result
