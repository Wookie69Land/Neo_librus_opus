from __future__ import annotations

import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.domain.isbn import normalise_isbn, validate_isbn
from app.domain.models import Book
from app.domain.seed_utils import apply_field_updates, prune_orphan_authors, sync_book_authors

SEED_FILE = Path(__file__).resolve().parents[2] / "seed_data" / "polish_books_top100_real_isbns.json"
DATA_SOURCE = "curated-polish-top100"
INTEGRATION_SOURCE = 20


class Command(BaseCommand):
    help = (
        "Seed the database with 100 curated famous Polish books and their authors "
        "from a local JSON file. Imports only titles with a verified real ISBN and "
        "reports unresolved books for manual bibliographic completion."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--replace-curated",
            action="store_true",
            help="Delete previously seeded curated books before importing the JSON file again.",
        )

    def handle(self, *args, **options):
        replace_curated: bool = options["replace_curated"]

        with SEED_FILE.open("r", encoding="utf-8") as seed_file:
            payload = json.load(seed_file)

        records: list[dict] = payload["books"]
        created = 0
        updated = 0
        skipped = 0
        unresolved: list[str] = []

        if replace_curated:
            with transaction.atomic():
                Book.objects.filter(data_source=DATA_SOURCE).delete()
                prune_orphan_authors()
            self.stdout.write("Deleted previously seeded curated books.")

        for record in records:
            isbn = record.get("isbn")
            if not isbn:
                unresolved.append(f"{record['title']} — {', '.join(record['authors'])}")
                self.stdout.write(
                    self.style.WARNING(
                        f"  [SKIPPED] {record['title']} — missing verified ISBN in curated seed file."
                    )
                )
                continue

            try:
                validate_isbn(isbn)
            except ValidationError as exc:
                raise CommandError(
                    f"Invalid ISBN in curated seed file for '{record['title']}': {'; '.join(exc.messages)}"
                ) from exc

            isbn = normalise_isbn(isbn)
            authors = record["authors"]
            author_label = ", ".join(authors)
            category = record["category"]
            defaults = {
                "title": record["title"],
                "integration_source": INTEGRATION_SOURCE,
                "data_source": DATA_SOURCE,
                "google_id": None,
                "publisher": record.get("publisher"),
                "published_year": record["published_year"],
                "description": record.get(
                    "description",
                    f"Kanoniczne dzieło literatury polskiej z kategorii {category.lower()}, autorstwa {author_label}.",
                ),
                "page_count": record.get("page_count"),
                "print_type": record.get("print_type", "PAPERBACK"),
                "category": category,
                "cover_url": record.get("cover_url"),
                "language": record.get("language", "pol"),
            }

            book = Book.objects.filter(isbn=isbn).first()
            if book is None:
                book = Book.objects.create(isbn=isbn, **defaults)
                sync_book_authors(book, authors)
                created += 1
                self.stdout.write(f"  [CREATED] {book.title}")
                continue

            changed_fields = apply_field_updates(book, defaults)
            authors_changed = sync_book_authors(book, authors)
            if changed_fields:
                book.save(update_fields=changed_fields)

            if changed_fields or authors_changed:
                updated += 1
                self.stdout.write(f"  [UPDATED] {book.title}")
            else:
                skipped += 1
                self.stdout.write(f"  [EXISTS ] {book.title}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created: {created}  |  Updated: {updated}  |  Exists/skipped: {skipped}"
            )
        )
        if unresolved:
            self.stdout.write(self.style.WARNING(f"Unresolved curated titles skipped: {len(unresolved)}"))
            for item in unresolved:
                self.stdout.write(f"  - {item}")
