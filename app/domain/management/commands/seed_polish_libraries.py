from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from app.domain.models import Library
from app.domain.seed_utils import apply_field_updates, normalise_email, normalise_phone, normalise_whitespace

SEED_FILE = Path(__file__).resolve().parents[2] / "seed_data" / "polish_libraries_top10.json"


class Command(BaseCommand):
    help = "Seed the database with 10 major Polish libraries from a curated local JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--replace-seeded",
            action="store_true",
            help="Delete existing libraries matching the curated names before reseeding.",
        )

    def handle(self, *args, **options):
        replace_seeded: bool = options["replace_seeded"]

        with SEED_FILE.open("r", encoding="utf-8") as seed_file:
            payload = json.load(seed_file)

        records: list[dict] = payload["libraries"]
        created = 0
        updated = 0
        skipped = 0

        if replace_seeded:
            library_names = [record["name"] for record in records]
            Library.objects.filter(name__in=library_names).delete()
            self.stdout.write("Deleted previously seeded libraries matching the curated dataset.")

        for record in records:
            defaults = {
                "address": normalise_whitespace(record["address"]),
                "city": normalise_whitespace(record["city"]),
                "phone": normalise_phone(record.get("phone")),
                "email": normalise_email(record.get("email")),
                "region": record["region"],
            }

            library = Library.objects.filter(
                name__iexact=record["name"],
                city__iexact=record["city"],
            ).first()

            if library is None:
                Library.objects.create(name=normalise_whitespace(record["name"]), **defaults)
                created += 1
                self.stdout.write(f"  [CREATED] {record['name']}")
                continue

            changed_fields = apply_field_updates(library, {"name": normalise_whitespace(record["name"]), **defaults})
            if changed_fields:
                library.save(update_fields=changed_fields)
                updated += 1
                self.stdout.write(f"  [UPDATED] {library.name}")
            else:
                skipped += 1
                self.stdout.write(f"  [EXISTS ] {library.name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created: {created}  |  Updated: {updated}  |  Exists/skipped: {skipped}"
            )
        )
