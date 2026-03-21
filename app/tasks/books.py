"""Scheduled ARQ jobs for cyclic book synchronization and enrichment."""
from __future__ import annotations

import asyncio
import io
import random
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management import call_command
from django.db.models import Count, Q
from django.utils import timezone

from app.domain.google_books import GoogleBooksClient, GoogleBooksTemporaryError
from app.domain.models import Book, CyclicTaskReport, Library, LibraryBook
from app.domain.seed_utils import sync_book_authors

BOOK_SYNC_LIMIT = 250
BOOK_SYNC_BATCH_SIZE = 10
BOOK_SYNC_STOP_THRESHOLD = 5000
BOOK_ENRICH_BATCH_SIZE = 100
BOOK_LIBRARY_MIN_ASSIGNMENTS = 2
BOOK_LIBRARY_MAX_ASSIGNMENTS = 5
BOOK_CATEGORY_MAX_LENGTH = 511


def _report_retention_limit() -> int:
    return max(getattr(settings, "CYCLIC_TASK_REPORT_RETENTION", 3), 1)


async def _prune_old_reports(task_name: str) -> None:
    report_ids_to_delete: list[int] = []
    retained = 0

    async for report_id in CyclicTaskReport.objects.filter(task_name=task_name).order_by(
        "-started_at", "-id"
    ).values_list("id", flat=True):
        retained += 1
        if retained > _report_retention_limit():
            report_ids_to_delete.append(report_id)

    if report_ids_to_delete:
        await CyclicTaskReport.objects.filter(id__in=report_ids_to_delete).adelete()


async def _save_task_report(
    *,
    task_name: str,
    status: str,
    started_at,
    finished_at,
    payload: dict[str, Any],
) -> None:
    duration_ms = max(int((finished_at - started_at).total_seconds() * 1000), 0)
    await CyclicTaskReport.objects.acreate(
        task_name=task_name,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        payload=payload,
    )
    await _prune_old_reports(task_name)


async def _run_with_report(
    task_name: str,
    task_callable,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    started_at = timezone.now()
    try:
        result = await task_callable(ctx)
    except Exception as exc:
        finished_at = timezone.now()
        await _save_task_report(
            task_name=task_name,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            payload={
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        raise

    finished_at = timezone.now()
    await _save_task_report(
        task_name=task_name,
        status=str(result.get("status", "completed")),
        started_at=started_at,
        finished_at=finished_at,
        payload=result,
    )
    return result


def _merge_categories(existing: str | None, incoming: list[str]) -> str | None:
    if not incoming:
        return existing

    merged: list[str] = []
    seen: set[str] = set()
    for raw_value in [*(existing or "").split(","), *incoming]:
        value = raw_value.strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)

    result = ", ".join(merged)
    return result[:BOOK_CATEGORY_MAX_LENGTH] if result else None


def _author_sync_needed(current_authors: list[str], proposed_authors: list[str]) -> bool:
    if not proposed_authors:
        return False
    if not current_authors:
        return True
    if len(current_authors) == len(proposed_authors) == 1:
        current_last = current_authors[0].split()[-1].casefold()
        proposed_last = proposed_authors[0].split()[-1].casefold()
        return current_last == proposed_last and current_authors[0] != proposed_authors[0]
    return False


async def _cyclic_book_seeder_impl(ctx: dict[str, Any]) -> dict[str, Any]:
    """Run the ISBN importer daily until the catalog reaches the configured cap."""

    current_count = await Book.objects.acount()
    if current_count > BOOK_SYNC_STOP_THRESHOLD:
        return {
            "status": "skipped",
            "reason": f"book-count-above-threshold:{current_count}",
        }

    stdout = io.StringIO()
    stderr = io.StringIO()
    await asyncio.to_thread(
        call_command,
        "fetch_isbn_books",
        limit=BOOK_SYNC_LIMIT,
        batch_size=BOOK_SYNC_BATCH_SIZE,
        no_verify_ssl=True,
        stdout=stdout,
        stderr=stderr,
    )
    return {
        "status": "completed",
        "before_count": current_count,
        "stdout": stdout.getvalue().strip(),
        "stderr": stderr.getvalue().strip(),
    }


async def _book_enricher_impl(ctx: dict[str, Any]) -> dict[str, Any]:
    """Fill missing Google Books metadata for up to 100 books each day."""

    client = GoogleBooksClient(
        api_key=ctx.get("google_books_api_key"),
        timeout=ctx.get("google_books_timeout", 15.0),
    )
    queryset = (
        Book.objects.filter(
            Q(cover_url__isnull=True)
            | Q(cover_url="")
            | Q(category__isnull=True)
            | Q(category="")
            | Q(google_id__isnull=True)
            | Q(google_id="")
        )
        .order_by("last_updated")[:BOOK_ENRICH_BATCH_SIZE]
    )

    enriched = 0
    author_updates = 0
    skipped = 0
    api_unavailable = False
    warning: str | None = None

    async for book in queryset:
        authors = [author.name async for author in book.authors.all()]
        try:
            best_match = await client.best_match(isbn=book.isbn, title=book.title, authors=authors)
        except GoogleBooksTemporaryError as exc:
            api_unavailable = True
            warning = str(exc)
            skipped += 1
            break

        if best_match is None:
            skipped += 1
            continue

        changed_fields: list[str] = []
        if best_match.google_id and book.google_id != best_match.google_id:
            book.google_id = best_match.google_id
            changed_fields.append("google_id")
        if best_match.cover_url and not book.cover_url:
            book.cover_url = best_match.cover_url
            changed_fields.append("cover_url")

        merged_category = _merge_categories(book.category, best_match.categories)
        if merged_category != book.category:
            book.category = merged_category
            changed_fields.append("category")

        if changed_fields:
            await sync_to_async(book.save)(update_fields=changed_fields)
            enriched += 1

        if _author_sync_needed(authors, best_match.authors):
            authors_changed = await sync_to_async(sync_book_authors)(book, best_match.authors)
            if authors_changed:
                author_updates += 1

    result = {
        "status": "completed_with_warnings" if api_unavailable else "completed",
        "enriched": enriched,
        "author_updates": author_updates,
        "skipped": skipped,
    }
    if api_unavailable and warning:
        result["warning"] = warning
        result["api_unavailable"] = True
    return result


async def _assign_books_to_random_libraries_impl(ctx: dict[str, Any]) -> dict[str, Any]:
    """Ensure books are assigned to at least two random libraries, up to five total."""

    library_ids = [library_id async for library_id in Library.objects.values_list("id", flat=True)]
    if len(library_ids) < BOOK_LIBRARY_MIN_ASSIGNMENTS:
        return {
            "status": "skipped",
            "reason": "not-enough-libraries",
            "library_count": len(library_ids),
        }

    books = []
    async for book in Book.objects.annotate(library_count=Count("librarybook")).filter(library_count__lt=BOOK_LIBRARY_MIN_ASSIGNMENTS):
        books.append(book)

    assignments_created = 0
    processed_books = 0

    for book in books:
        assigned_ids = {
            library_id
            async for library_id in LibraryBook.objects.filter(book=book).values_list("library_id", flat=True)
        }
        target_total = random.randint(BOOK_LIBRARY_MIN_ASSIGNMENTS, min(BOOK_LIBRARY_MAX_ASSIGNMENTS, len(library_ids)))
        target_total = max(target_total, BOOK_LIBRARY_MIN_ASSIGNMENTS)

        available_ids = [library_id for library_id in library_ids if library_id not in assigned_ids]
        slots_to_fill = max(BOOK_LIBRARY_MIN_ASSIGNMENTS - len(assigned_ids), target_total - len(assigned_ids))
        slots_to_fill = min(slots_to_fill, len(available_ids))

        if slots_to_fill <= 0:
            continue

        for library_id in random.sample(available_ids, slots_to_fill):
            _, created = await LibraryBook.objects.aget_or_create(
                book=book,
                library_id=library_id,
                defaults={"is_available": True},
            )
            if created:
                assignments_created += 1

        processed_books += 1

    return {
        "status": "completed",
        "processed_books": processed_books,
        "assignments_created": assignments_created,
    }


async def _cyclic_book_manager_impl(ctx: dict[str, Any]) -> dict[str, Any]:
    """Run daily enrichment and library assignment maintenance."""

    enrich_result = await _book_enricher_impl(ctx)
    assignment_result = await _assign_books_to_random_libraries_impl(ctx)
    return {
        "status": "completed",
        "book_enricher": enrich_result,
        "library_assignment": assignment_result,
    }


async def cyclic_book_seeder(ctx: dict[str, Any]) -> dict[str, Any]:
    """Run the ISBN importer daily until the catalog reaches the configured cap."""

    return await _run_with_report("cyclic_book_seeder", _cyclic_book_seeder_impl, ctx)


async def book_enricher(ctx: dict[str, Any]) -> dict[str, Any]:
    """Fill missing Google Books metadata for up to 100 books each day."""

    return await _run_with_report("book_enricher", _book_enricher_impl, ctx)


async def assign_books_to_random_libraries(ctx: dict[str, Any]) -> dict[str, Any]:
    """Ensure books are assigned to at least two random libraries, up to five total."""

    return await _run_with_report(
        "assign_books_to_random_libraries",
        _assign_books_to_random_libraries_impl,
        ctx,
    )


async def cyclic_book_manager(ctx: dict[str, Any]) -> dict[str, Any]:
    """Run daily enrichment and library assignment maintenance."""

    return await _run_with_report("cyclic_book_manager", _cyclic_book_manager_impl, ctx)
