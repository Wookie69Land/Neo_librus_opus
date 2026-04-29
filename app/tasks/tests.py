from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import TestCase
from django.utils import timezone

from app.domain.models import Author, Book, Library, LibraryBook, LibraryUser, Reservation, Status
from app.tasks.books import (
    _assign_books_to_random_libraries_impl,
    _book_enricher_impl,
)
from app.domain.google_books import GoogleBooksTemporaryError, GoogleBooksVolume
from app.tasks.reservations import _reservation_manager_impl


class BookEnricherTests(TestCase):
    def setUp(self) -> None:
        self.author = Author.objects.create(name="Tomasz Witkowski")

    def _create_book(self, *, isbn: str, title: str) -> Book:
        book = Book.objects.create(title=title, isbn=isbn)
        book.authors.add(self.author)
        return book

    def test_no_match_defers_book_and_tracks_attempt(self) -> None:
        book = self._create_book(isbn="9780306406157", title="No Match Book")

        with patch("app.tasks.books.GoogleBooksClient.best_match", new=AsyncMock(return_value=None)):
            result = async_to_sync(_book_enricher_impl)({})

        book.refresh_from_db()
        self.assertEqual(result["examined"], 1)
        self.assertEqual(result["no_match"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertTrue(book.google_checked)

    def test_temporary_failure_defers_one_book_and_continues_batch(self) -> None:
        failed_book = self._create_book(isbn="9780140328721", title="429 Book")
        successful_book = self._create_book(isbn="9780747532743", title="Good Book")
        volume = GoogleBooksVolume(
            google_id="google-1",
            title="Good Book",
            authors=["Tomasz Witkowski"],
            categories=["Psychology"],
            cover_url="https://example.com/cover.jpg",
            raw={},
        )

        with patch(
            "app.tasks.books.GoogleBooksClient.best_match",
            new=AsyncMock(side_effect=[GoogleBooksTemporaryError("429"), volume]),
        ):
            result = async_to_sync(_book_enricher_impl)({})

        failed_book.refresh_from_db()
        successful_book.refresh_from_db()
        self.assertEqual(result["examined"], 2)
        self.assertEqual(result["temporary_failures"], 1)
        self.assertEqual(result["enriched"], 1)
        self.assertTrue(failed_book.google_checked)
        self.assertTrue(successful_book.google_checked)
        self.assertEqual(successful_book.google_id, "google-1")
        self.assertEqual(successful_book.category, "Psychology")


class LibraryAssignmentTests(TestCase):
    def test_assignment_report_contains_created_library_ids(self) -> None:
        libraries = [
            Library.objects.create(name="Library A"),
            Library.objects.create(name="Library B"),
            Library.objects.create(name="Library C"),
        ]
        book = Book.objects.create(title="Assigned Book", isbn="9780590353427")
        LibraryBook.objects.create(book=book, library=libraries[0], is_available=True)

        with patch("app.tasks.books.random.randint", return_value=3), patch(
            "app.tasks.books.random.sample", return_value=[libraries[1].id, libraries[2].id]
        ):
            result = async_to_sync(_assign_books_to_random_libraries_impl)({})

        self.assertEqual(result["processed_books"], 1)
        self.assertEqual(result["assignments_created"], 2)
        self.assertEqual(len(result["assignment_samples"]), 1)
        self.assertEqual(
            result["assignment_samples"][0]["created_library_ids"],
            [libraries[1].id, libraries[2].id],
        )


class ReservationManagerTaskTests(TestCase):
    """Unit tests for the reservation_manager background task."""

    def setUp(self) -> None:
        self.library = Library.objects.create(name="Test Library")
        self.book = Book.objects.create(title="Task Test Book", isbn="9780000000099")
        self.reader = LibraryUser.objects.create_user(
            username="task_reader", email="task_reader@example.com", password="secret"
        )
        for name in ("pending", "accepted", "rejected", "expired", "cancelled", "closed"):
            Status.objects.get_or_create(name=name)
        self.pending_status = Status.objects.get(name="pending")
        self.accepted_status = Status.objects.get(name="accepted")
        self.expired_status = Status.objects.get(name="expired")
        self.closed_status = Status.objects.get(name="closed")

    def _make_reservation(self, status: Status) -> Reservation:
        return Reservation.objects.create(
            reader=self.reader,
            library=self.library,
            book=self.book,
            status=status,
        )

    def test_pending_older_than_48h_is_expired(self) -> None:
        reservation = self._make_reservation(self.pending_status)
        Reservation.objects.filter(pk=reservation.pk).update(
            updated_at=timezone.now() - timedelta(hours=49)
        )

        result = async_to_sync(_reservation_manager_impl)()

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, self.expired_status)
        self.assertEqual(result["expired"], 1)
        self.assertEqual(result["closed"], 0)

    def test_recent_pending_reservation_is_not_expired(self) -> None:
        reservation = self._make_reservation(self.pending_status)
        Reservation.objects.filter(pk=reservation.pk).update(
            updated_at=timezone.now() - timedelta(hours=24)
        )

        result = async_to_sync(_reservation_manager_impl)()

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, self.pending_status)
        self.assertEqual(result["expired"], 0)

    def test_accepted_older_than_3_days_is_closed(self) -> None:
        reservation = self._make_reservation(self.accepted_status)
        Reservation.objects.filter(pk=reservation.pk).update(
            updated_at=timezone.now() - timedelta(days=4)
        )

        result = async_to_sync(_reservation_manager_impl)()

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, self.closed_status)
        self.assertEqual(result["closed"], 1)
        self.assertEqual(result["expired"], 0)

    def test_recent_accepted_reservation_is_not_closed(self) -> None:
        reservation = self._make_reservation(self.accepted_status)
        Reservation.objects.filter(pk=reservation.pk).update(
            updated_at=timezone.now() - timedelta(hours=12)
        )

        result = async_to_sync(_reservation_manager_impl)()

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, self.accepted_status)
        self.assertEqual(result["closed"], 0)

    def test_multiple_reservations_processed_independently(self) -> None:
        stale_pending = self._make_reservation(self.pending_status)
        stale_accepted = self._make_reservation(self.accepted_status)
        fresh_pending = self._make_reservation(self.pending_status)

        Reservation.objects.filter(pk=stale_pending.pk).update(
            updated_at=timezone.now() - timedelta(hours=49)
        )
        Reservation.objects.filter(pk=stale_accepted.pk).update(
            updated_at=timezone.now() - timedelta(days=4)
        )
        Reservation.objects.filter(pk=fresh_pending.pk).update(
            updated_at=timezone.now() - timedelta(hours=10)
        )

        result = async_to_sync(_reservation_manager_impl)()

        stale_pending.refresh_from_db()
        stale_accepted.refresh_from_db()
        fresh_pending.refresh_from_db()

        self.assertEqual(stale_pending.status, self.expired_status)
        self.assertEqual(stale_accepted.status, self.closed_status)
        self.assertEqual(fresh_pending.status, self.pending_status)
        self.assertEqual(result["expired"], 1)
        self.assertEqual(result["closed"], 1)