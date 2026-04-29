"""Management command that seeds minimal test data for manual reservation flow testing.

Run inside the container:

    python manage.py seed_reservation_test_data

The command is idempotent — running it again does not create duplicates.
It prints ready-to-use curl commands for the full reservation flow at the end.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand

from app.api.jwt_utils import encode_token
from app.domain.models import (
    Book,
    Library,
    LibraryAdmin,
    LibraryBook,
    LibraryUser,
    Role,
    SessionToken,
    Status,
)

BASE_URL = "http://localhost:8000"

# ── credentials ──────────────────────────────────────────────────────────────
READER_USERNAME = "test_reader"
READER_EMAIL = "lukaskraj@gmail.com"
READER_PASSWORD = "WookiePass1!"

ADMIN_USERNAME = "test_libadmin"
ADMIN_EMAIL = "lukaskraj@gmail.com"
ADMIN_PASSWORD = "WookiePass1!"


def _make_token(user: LibraryUser, role_id: int = 0, library_id: int = 0) -> str:
    return encode_token(
        {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "region": user.region,
            "date_joined": user.date_joined.isoformat(),
            "role_id": role_id,
            "library_id": library_id,
            "jti": str(uuid.uuid4()),
        }
    )


class Command(BaseCommand):
    help = "Seed minimal test data for manual reservation flow testing."

    def handle(self, *args, **options) -> None:
        self.stdout.write("Seeding reservation test data…")

        # ── statuses ─────────────────────────────────────────────────────────
        for name in ("pending", "accepted", "rejected", "expired", "cancelled", "closed"):
            Status.objects.get_or_create(name=name)

        # ── role ─────────────────────────────────────────────────────────────
        role, _ = Role.objects.get_or_create(name="library_admin_test")

        # ── library — use first existing one ─────────────────────────────────
        library = Library.objects.first()
        if library is None:
            raise SystemExit("No libraries found in the database. Seed libraries first.")

        # ── book — use first existing one, link it to the library ────────────
        book = Book.objects.first()
        if book is None:
            raise SystemExit("No books found in the database. Seed books first.")
        LibraryBook.objects.get_or_create(book=book, library=library, defaults={"is_available": True})

        # ── reader user ──────────────────────────────────────────────────────
        reader = LibraryUser.objects.filter(username=READER_USERNAME).first()
        if reader is None:
            reader = LibraryUser.objects.create_user(
                username=READER_USERNAME,
                email=READER_EMAIL,
                password=READER_PASSWORD,
                first_name="Test",
                last_name="Reader",
                is_active=True,
            )
        reader.refresh_from_db()
        reader_token = _make_token(reader)
        SessionToken.objects.update_or_create(user=reader, defaults={"key": reader_token})

        # ── library admin user ───────────────────────────────────────────────
        admin = LibraryUser.objects.filter(username=ADMIN_USERNAME).first()
        if admin is None:
            admin = LibraryUser.objects.create_user(
                username=ADMIN_USERNAME,
                email=ADMIN_EMAIL,
                password=ADMIN_PASSWORD,
                first_name="Test",
                last_name="LibAdmin",
                is_active=True,
            )
        admin.refresh_from_db()
        admin_token = _make_token(admin, role_id=role.id, library_id=library.id)
        SessionToken.objects.update_or_create(user=admin, defaults={"key": admin_token})
        LibraryAdmin.objects.get_or_create(library=library, user=admin, defaults={"role": role})

        self.stdout.write(self.style.SUCCESS("Done. Test data created.\n"))
        self._print_guide(library, book, reader_token, admin_token)

    def _print_guide(
        self,
        library: Library,
        book: Book,
        reader_token: str,
        admin_token: str,
    ) -> None:
        b = BASE_URL
        lib = library.id
        bk = book.id
        sep = "-" * 70

        lines = [
            sep,
            "  RESERVATION FLOW — MANUAL TEST GUIDE",
            sep,
            "",
            "Export tokens:",
            f'  READER="{reader_token}"',
            f'  ADMIN="{admin_token}"',
            "",
            "── 1. CREATE reservation (reader) ──────────────────────────────────",
            f'  curl -s -X POST {b}/api/reservations \\',
            f'    -H "Authorization: Bearer $READER" \\',
            f'    -H "Content-Type: application/json" \\',
            f'    -d \'{{"library_id": {lib}, "book_id": {bk}}}\'',
            "  → status: pending",
            "  → copy the returned 'id' as $RID",
            "",
            "── 2a. ACCEPT reservation (admin) ──────────────────────────────────",
            "  ACCEPTED_STATUS=$(curl -s http://localhost:8000/api/statuses \\",
            '    -H "Authorization: Bearer $ADMIN" | \\',
            '    python3 -c "import sys,json; data=json.load(sys.stdin);',
            "    print(next(s['id'] for s in data if s['name']=='accepted'))\")",
            "",
            f'  curl -s -X PUT {b}/api/reservations/$RID \\',
            f'    -H "Authorization: Bearer $ADMIN" \\',
            f'    -H "Content-Type: application/json" \\',
            f'    -d \'{{"status_id": $ACCEPTED_STATUS}}\'',
            "  → status: accepted",
            "",
            "── 2b. REJECT reservation (admin, alternative) ─────────────────────",
            "  REJECTED_STATUS=$(curl -s http://localhost:8000/api/statuses \\",
            '    -H "Authorization: Bearer $ADMIN" | \\',
            '    python3 -c "import sys,json; data=json.load(sys.stdin);',
            "    print(next(s['id'] for s in data if s['name']=='rejected'))\")",
            "",
            f'  curl -s -X PUT {b}/api/reservations/$RID \\',
            f'    -H "Authorization: Bearer $ADMIN" \\',
            f'    -H "Content-Type: application/json" \\',
            f'    -d \'{{"status_id": $REJECTED_STATUS}}\'',
            "  → status: rejected",
            "",
            "── 3. CANCEL reservation (reader, from pending or accepted) ─────────",
            f'  curl -s -X DELETE {b}/api/reservations/$RID \\',
            f'    -H "Authorization: Bearer $READER"',
            "  → status: cancelled",
            "",
            "── 4. CHECK reservation state ───────────────────────────────────────",
            f'  curl -s {b}/api/reservations/$RID \\',
            f'    -H "Authorization: Bearer $READER"',
            "",
            "── 5. LIST reservations (reader sees own, admin sees library's) ─────",
            f'  curl -s {b}/api/reservations \\',
            f'    -H "Authorization: Bearer $READER"',
            "",
            f'  curl -s {b}/api/reservations \\',
            f'    -H "Authorization: Bearer $ADMIN"',
            "",
            "── 6. SIMULATE system expiry (pending → expired after 48 h) ─────────",
            "  # Fast-forward the updated_at timestamp manually:",
            "  python manage.py shell -c \"",
            "  from django.utils import timezone; from datetime import timedelta",
            "  from app.domain.models import Reservation",
            "  Reservation.objects.filter(status__name='pending').update(",
            "      updated_at=timezone.now() - timedelta(hours=49))\"",
            "",
            "  # Then run the manager task:",
            "  python manage.py run_cyclic_task reservation_manager",
            "",
            "── 7. SIMULATE system closure (accepted → closed after 3 days) ──────",
            "  python manage.py shell -c \"",
            "  from django.utils import timezone; from datetime import timedelta",
            "  from app.domain.models import Reservation",
            "  Reservation.objects.filter(status__name='accepted').update(",
            "      updated_at=timezone.now() - timedelta(days=4))\"",
            "",
            "  python manage.py run_cyclic_task reservation_manager",
            "",
            sep,
        ]
        self.stdout.write("\n".join(lines))
