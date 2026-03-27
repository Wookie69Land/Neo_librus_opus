from __future__ import annotations

from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import TestCase

from app.domain.models import Author, Book, Library, LibraryBook
from app.tasks.books import (
    _assign_books_to_random_libraries_impl,
    _book_enricher_impl,
)
from app.domain.google_books import GoogleBooksTemporaryError, GoogleBooksVolume


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