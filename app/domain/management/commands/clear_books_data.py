from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.domain.models import Author, Book, BookAuthor


class Command(BaseCommand):
    help = (
        "Delete all rows from Author, BookAuthor, and Book. "
        "Use to remove imported or test catalog data before a fresh reimport."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete data without interactive confirmation.",
        )

    def handle(self, *args, **options):
        force: bool = options["force"]

        author_count = Author.objects.count()
        book_author_count = BookAuthor.objects.count()
        book_count = Book.objects.count()

        self.stdout.write(
            "This will delete all rows from Author, BookAuthor, and Book."
        )
        self.stdout.write(
            f"Current counts: authors={author_count}, book_links={book_author_count}, books={book_count}"
        )

        if not force:
            confirmation = input("Type DELETE to confirm: ").strip()
            if confirmation != "DELETE":
                raise CommandError("Aborted. No data was deleted.")

        with transaction.atomic():
            deleted_book_authors, _ = BookAuthor.objects.all().delete()
            deleted_books, _ = Book.objects.all().delete()
            deleted_authors, _ = Author.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Deleted rows: "
                f"BookAuthor={deleted_book_authors}, Book={deleted_books}, Author={deleted_authors}"
            )
        )