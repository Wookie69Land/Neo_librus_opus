"""Management command that generates randomised factory data for manual and exploratory testing.

Creates libraries, books, authors, readers, library-admin users, and reservations in
every possible status so that the full API surface can be exercised immediately after
deployment.

All generated objects use a ``factory_`` prefix on usernames and a distinctive library
name prefix so they can be found and removed later with ``--clear``.

Usage
-----

    # Seed with defaults (3 libraries, 15 books, 8 readers, 30 extra reservations)
    python manage.py seed_factory_data

    # Larger dataset
    python manage.py seed_factory_data --libraries 5 --books 30 --readers 20 --extra-reservations 60

    # Remove all previously generated factory objects, then reseed
    python manage.py seed_factory_data --clear

    # Remove without reseeding
    python manage.py seed_factory_data --clear --only-clear
"""
from __future__ import annotations

import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from app.api.jwt_utils import encode_token
from app.domain.models import (
    Author,
    Book,
    BookAuthor,
    Library,
    LibraryAdmin,
    LibraryBook,
    LibraryUser,
    Reservation,
    Role,
    SessionToken,
    Status,
    Voivodeship,
)

# ── Marker prefix — all generated objects carry this so --clear can find them ──
_PREFIX = "factory_"

# ── Default password for every generated user account ─────────────────────────
_DEFAULT_PASSWORD = "WookiePass1!"

# ── Fixture data pools ─────────────────────────────────────────────────────────
_CITIES = [
    ("Warszawa", Voivodeship.MAZOWIECKIE),
    ("Kraków", Voivodeship.MALOPOLSKIE),
    ("Wrocław", Voivodeship.DOLNOSLASKIE),
    ("Gdańsk", Voivodeship.POMORSKIE),
    ("Poznań", Voivodeship.WIELKOPOLSKIE),
    ("Łódź", Voivodeship.LODZKIE),
    ("Katowice", Voivodeship.SLASKIE),
    ("Lublin", Voivodeship.LUBELSKIE),
    ("Białystok", Voivodeship.PODLASKIE),
    ("Rzeszów", Voivodeship.PODKARPACKIE),
]

_STREET_NAMES = [
    "Główna", "Lipowa", "Polna", "Szkolna", "Leśna",
    "Różana", "Słoneczna", "Ogrodowa", "Nowa", "Krótka",
]

_FIRST_NAMES = [
    "Anna", "Marek", "Katarzyna", "Piotr", "Zofia",
    "Tomasz", "Agnieszka", "Michał", "Elżbieta", "Jan",
    "Barbara", "Krzysztof", "Monika", "Andrzej", "Joanna",
    "Stanisław", "Maria", "Paweł", "Magdalena", "Łukasz",
]

_LAST_NAMES = [
    "Kowalski", "Nowak", "Wiśniewski", "Dąbrowski", "Lewandowski",
    "Wójcik", "Kamiński", "Kowalczyk", "Zieliński", "Szymański",
    "Woźniak", "Kozłowski", "Jankowski", "Mazur", "Kwiatkowski",
    "Krawczyk", "Piotrowski", "Grabowski", "Nowakowski", "Pawłowski",
]

_BOOK_TITLES = [
    "Zagubiony czas", "Cień przyszłości", "Dom na wzgórzu", "Podróż do końca świata",
    "Ostatnie słowo", "Niebieska góra", "Wieczór nad morzem", "Tajemnica starego zamku",
    "Głosy z przeszłości", "Nowy świat", "Burza nad miastem", "Cisza przed świtem",
    "Kraina lodu", "Złoty wiek", "Powrót do domu", "Droga przez las",
    "Serce nocy", "Rzeka wspomnień", "Miasto mgieł", "Koniec lata",
    "Pierwszy krok", "Biała noc", "Echa dawnych dni", "Poszukiwacze prawdy",
    "Nieznajomy z północy", "Labirynt snów", "Opowieść o czasie", "Morze spokoju",
    "Zielona dolina", "Strażnik ognia",
]

_AUTHOR_NAMES = [
    "Adam Mickiewicz", "Wisława Szymborska", "Stanisław Lem", "Olga Tokarczuk",
    "Ryszard Kapuściński", "Bolesław Prus", "Henryk Sienkiewicz", "Maria Konopnicka",
    "Juliusz Słowacki", "Sławomir Mrożek", "Tadeusz Różewicz", "Andrzej Sapkowski",
    "Marek Krajewski", "Zygmunt Miłoszewski", "Katarzyna Bonda",
]

_ALL_STATUSES = ("pending", "accepted", "rejected", "expired", "cancelled", "closed")


# ── ISBN-13 generation ─────────────────────────────────────────────────────────

def _isbn13_check_digit(digits_12: str) -> str:
    total = sum(
        int(d) * (1 if i % 2 == 0 else 3)
        for i, d in enumerate(digits_12)
    )
    return str((10 - (total % 10)) % 10)


def _make_isbn13(seed: int) -> str:
    """Generate a valid ISBN-13 deterministically from an integer seed."""
    core = f"978{seed:09d}"[:12]
    return core + _isbn13_check_digit(core)


# ── Token helper ───────────────────────────────────────────────────────────────

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


# ── Random helpers ─────────────────────────────────────────────────────────────

def _pick(pool: list, exclude: set | None = None) -> str:
    candidates = [x for x in pool if x not in (exclude or set())]
    return random.choice(candidates)


class Command(BaseCommand):
    help = (
        "Generate randomised factory data for testing "
        "(libraries, books, authors, users, reservations in all statuses)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--libraries", type=int, default=3,
            help="Number of factory libraries to create (default: 3).",
        )
        parser.add_argument(
            "--books", type=int, default=15,
            help="Number of factory books to create (default: 15).",
        )
        parser.add_argument(
            "--readers", type=int, default=8,
            help="Number of factory reader accounts to create (default: 8).",
        )
        parser.add_argument(
            "--extra-reservations", type=int, default=30,
            help="Extra random reservations to create beyond the one-per-status set (default: 30).",
        )
        parser.add_argument(
            "--password", default=_DEFAULT_PASSWORD,
            help=f"Password for all generated accounts (default: {_DEFAULT_PASSWORD}).",
        )
        parser.add_argument(
            "--clear", action="store_true",
            help="Remove all previously generated factory objects before seeding.",
        )
        parser.add_argument(
            "--only-clear", action="store_true",
            help="Only remove factory objects; do not seed new ones.",
        )

    def handle(self, *args, **options) -> None:
        rng = random.Random(42)  # reproducible by default; shuffle after creation

        if options["clear"] or options["only_clear"]:
            self._clear()
            if options["only_clear"]:
                return

        n_libs = options["libraries"]
        n_books = options["books"]
        n_readers = options["readers"]
        n_extra = options["extra_reservations"]
        password = options["password"]

        self.stdout.write("Seeding factory data…")

        statuses = self._ensure_statuses()
        role = self._ensure_role()
        libraries = self._create_libraries(n_libs, rng)
        authors = self._create_authors(rng)
        books = self._create_books(n_books, authors, libraries, rng)
        readers = self._create_readers(n_readers, password, rng)
        admins = self._create_admins(libraries, password, role, rng)
        self._create_reservations(books, libraries, readers, admins, statuses, rng)
        self._create_extra_reservations(books, libraries, readers, admins, statuses, n_extra, rng)

        self.stdout.write(self.style.SUCCESS(
            f"\nFactory data ready.\n"
            f"  Libraries : {len(libraries)}\n"
            f"  Books     : {len(books)}\n"
            f"  Authors   : {len(authors)}\n"
            f"  Readers   : {len(readers)}\n"
            f"  Admins    : {len(admins)} (one per library)\n"
            f"  Extra res.: {n_extra} additional random reservations\n"
        ))
        self._print_credentials(readers, admins, password)

    # ── clear ──────────────────────────────────────────────────────────────────

    def _clear(self) -> None:
        self.stdout.write("Clearing previous factory data…")

        # users (cascade deletes sessions, reservations-as-reader/librarian, LibraryAdmin rows)
        deleted_users, _ = LibraryUser.objects.filter(
            username__startswith=_PREFIX
        ).delete()

        # books created by this command (ISBN prefix 978000)
        deleted_books, _ = Book.objects.filter(isbn__startswith="978000").delete()

        # libraries
        deleted_libs, _ = Library.objects.filter(
            name__startswith=f"{_PREFIX}library"
        ).delete()

        self.stdout.write(
            f"  Removed {deleted_users} users, {deleted_books} books, "
            f"{deleted_libs} libraries."
        )

    # ── statuses ───────────────────────────────────────────────────────────────

    def _ensure_statuses(self) -> dict[str, Status]:
        result = {}
        for name in _ALL_STATUSES:
            obj, _ = Status.objects.get_or_create(name=name)
            result[name] = obj
        return result

    # ── role ───────────────────────────────────────────────────────────────────

    def _ensure_role(self) -> Role:
        role, _ = Role.objects.get_or_create(name=f"{_PREFIX}admin_role")
        return role

    # ── libraries ──────────────────────────────────────────────────────────────

    def _create_libraries(self, n: int, rng: random.Random) -> list[Library]:
        libraries = []
        city_pool = list(_CITIES)
        rng.shuffle(city_pool)
        for i in range(1, n + 1):
            name = f"{_PREFIX}library_{i}"
            obj = Library.objects.filter(name=name).first()
            if obj is None:
                city, region = city_pool[(i - 1) % len(city_pool)]
                street = rng.choice(_STREET_NAMES)
                number = rng.randint(1, 99)
                obj = Library.objects.create(
                    name=name,
                    city=city,
                    address=f"ul. {street} {number}",
                    region=region,
                )
            libraries.append(obj)
        return libraries

    # ── authors ────────────────────────────────────────────────────────────────

    def _create_authors(self, rng: random.Random) -> list[Author]:
        authors = []
        pool = list(_AUTHOR_NAMES)
        rng.shuffle(pool)
        for name in pool:
            obj, _ = Author.objects.get_or_create(name=name)
            authors.append(obj)
        return authors

    # ── books ──────────────────────────────────────────────────────────────────

    def _create_books(
        self,
        n: int,
        authors: list[Author],
        libraries: list[Library],
        rng: random.Random,
    ) -> list[Book]:
        books = []
        title_pool = list(_BOOK_TITLES)
        rng.shuffle(title_pool)

        for i in range(1, n + 1):
            isbn = _make_isbn13(i * 1000 + 100)
            title = title_pool[(i - 1) % len(title_pool)]

            obj = Book.objects.filter(isbn=isbn).first()
            if obj is None:
                obj = Book.objects.create(
                    title=title,
                    isbn=isbn,
                    language="pol",
                    published_year=rng.randint(1990, 2024),
                )
                # assign 1-2 authors
                chosen_authors = rng.sample(authors, k=min(2, len(authors)))
                for author in chosen_authors:
                    BookAuthor.objects.get_or_create(book=obj, author=author)

            # link to 1-3 libraries
            target_libs = rng.sample(libraries, k=min(rng.randint(1, 3), len(libraries)))
            for lib in target_libs:
                LibraryBook.objects.get_or_create(
                    book=obj, library=lib,
                    defaults={"is_available": True},
                )

            books.append(obj)
        return books

    # ── readers ────────────────────────────────────────────────────────────────

    def _create_readers(
        self, n: int, password: str, rng: random.Random
    ) -> list[LibraryUser]:
        readers = []
        used_names: set[str] = set()
        for i in range(1, n + 1):
            username = f"{_PREFIX}reader_{i}"
            obj = LibraryUser.objects.filter(username=username).first()
            if obj is None:
                first = _pick(_FIRST_NAMES, used_names)
                used_names.add(first)
                last = rng.choice(_LAST_NAMES)
                obj = LibraryUser.objects.create_user(
                    username=username,
                    email=f"{username}@factory.test",
                    password=password,
                    first_name=first,
                    last_name=last,
                    is_active=True,
                    region=rng.choice(list(Voivodeship)).value,
                )
            obj.refresh_from_db()
            token = _make_token(obj)
            SessionToken.objects.update_or_create(user=obj, defaults={"key": token})
            readers.append(obj)
        return readers

    # ── admins ─────────────────────────────────────────────────────────────────

    def _create_admins(
        self,
        libraries: list[Library],
        password: str,
        role: Role,
        rng: random.Random,
    ) -> list[LibraryUser]:
        admins = []
        for i, library in enumerate(libraries, start=1):
            username = f"{_PREFIX}admin_{i}"
            obj = LibraryUser.objects.filter(username=username).first()
            if obj is None:
                first = rng.choice(_FIRST_NAMES)
                last = rng.choice(_LAST_NAMES)
                obj = LibraryUser.objects.create_user(
                    username=username,
                    email=f"{username}@factory.test",
                    password=password,
                    first_name=first,
                    last_name=last,
                    is_active=True,
                )
            obj.refresh_from_db()
            token = _make_token(obj, role_id=role.id, library_id=library.id)
            SessionToken.objects.update_or_create(user=obj, defaults={"key": token})
            LibraryAdmin.objects.get_or_create(
                library=library, user=obj, defaults={"role": role}
            )
            admins.append(obj)
        return admins

    # ── reservations ───────────────────────────────────────────────────────────

    def _create_reservations(
        self,
        books: list[Book],
        libraries: list[Library],
        readers: list[LibraryUser],
        admins: list[LibraryUser],
        statuses: dict[str, Status],
        rng: random.Random,
    ) -> None:
        """Create one reservation per status per library so every flow is represented."""
        now = timezone.now()

        # Map admin → library for librarian assignment
        admin_by_lib: dict[int, LibraryUser] = {}
        for i, lib in enumerate(libraries):
            if i < len(admins):
                admin_by_lib[lib.id] = admins[i]

        created = 0
        for lib in libraries:
            librarian = admin_by_lib.get(lib.id)

            # Candidate books available at this library
            lib_books = [
                lb.book for lb in LibraryBook.objects.filter(library=lib).select_related("book")
            ]
            if not lib_books:
                continue

            for status_name, status_obj in statuses.items():
                reader = rng.choice(readers)
                book = rng.choice(lib_books)

                # Skip if this reader already has a reservation for this book/library
                if Reservation.objects.filter(
                    reader=reader, library=lib, book=book, status=status_obj
                ).exists():
                    continue

                needs_end_time = status_name in ("cancelled", "rejected", "expired", "closed")
                needs_librarian = status_name in ("accepted", "rejected", "closed")

                reservation = Reservation(
                    status=status_obj,
                    reader=reader,
                    librarian=librarian if needs_librarian else None,
                    library=lib,
                    book=book,
                    end_time=now if needs_end_time else None,
                )
                reservation.save()

                # Back-date updated_at so planned_end_time logic is realistic
                if status_name == "pending":
                    age_hours = rng.randint(1, 24)
                    Reservation.objects.filter(pk=reservation.pk).update(
                        updated_at=now - timedelta(hours=age_hours)
                    )
                elif status_name == "accepted":
                    age_hours = rng.randint(1, 48)
                    Reservation.objects.filter(pk=reservation.pk).update(
                        updated_at=now - timedelta(hours=age_hours)
                    )

                created += 1

        self.stdout.write(f"  Reservations created (one-per-status) : {created}")

    def _create_extra_reservations(
        self,
        books: list[Book],
        libraries: list[Library],
        readers: list[LibraryUser],
        admins: list[LibraryUser],
        statuses: dict[str, Status],
        n_extra: int,
        rng: random.Random,
    ) -> None:
        """Create N additional random reservations to fill pagination pages."""
        if n_extra <= 0:
            return

        now = timezone.now()
        admin_by_lib: dict[int, LibraryUser] = {
            lib.id: admins[i] for i, lib in enumerate(libraries) if i < len(admins)
        }
        status_list = list(statuses.values())
        status_names = list(statuses.keys())

        # Pre-fetch LibraryBook links so we can pick valid (book, library) pairs
        lib_books_map: dict[int, list[Book]] = {lib.id: [] for lib in libraries}
        for lb in LibraryBook.objects.filter(library__in=libraries).select_related("book"):
            lib_books_map[lb.library_id].append(lb.book)

        created = 0
        attempts = 0
        max_attempts = n_extra * 5  # avoid infinite loop on very small datasets

        while created < n_extra and attempts < max_attempts:
            attempts += 1
            lib = rng.choice(libraries)
            lib_books = lib_books_map.get(lib.id, [])
            if not lib_books:
                continue

            status_idx = rng.randrange(len(status_list))
            status_obj = status_list[status_idx]
            status_name = status_names[status_idx]
            reader = rng.choice(readers)
            book = rng.choice(lib_books)
            librarian = admin_by_lib.get(lib.id)

            needs_end_time = status_name in ("cancelled", "rejected", "expired", "closed")
            needs_librarian = status_name in ("accepted", "rejected", "closed")

            reservation = Reservation(
                status=status_obj,
                reader=reader,
                librarian=librarian if needs_librarian else None,
                library=lib,
                book=book,
                end_time=now if needs_end_time else None,
            )
            reservation.save()

            if status_name == "pending":
                Reservation.objects.filter(pk=reservation.pk).update(
                    updated_at=now - timedelta(hours=rng.randint(1, 47))
                )
            elif status_name == "accepted":
                Reservation.objects.filter(pk=reservation.pk).update(
                    updated_at=now - timedelta(hours=rng.randint(1, 71))
                )
            elif status_name in ("closed", "expired", "rejected", "cancelled"):
                days_ago = rng.randint(1, 60)
                Reservation.objects.filter(pk=reservation.pk).update(
                    updated_at=now - timedelta(days=days_ago)
                )

            created += 1

        self.stdout.write(f"  Reservations created (extra random)   : {created}")

    # ── credentials summary ────────────────────────────────────────────────────

    def _print_credentials(
        self,
        readers: list[LibraryUser],
        admins: list[LibraryUser],
        password: str,
    ) -> None:
        sep = "-" * 60
        lines = [
            "",
            sep,
            "  FACTORY ACCOUNTS",
            sep,
            f"  Password (all accounts): {password}",
            "",
            "  Readers:",
        ]
        for r in readers:
            token = SessionToken.objects.filter(user=r).values_list("key", flat=True).first() or ""
            lines.append(f"    {r.username}")
            lines.append(f"      {token}")

        lines += ["", "  Library admins:"]
        for a in admins:
            la = LibraryAdmin.objects.filter(user=a).select_related("library").first()
            lib_name = la.library.name if la else "?"
            token = SessionToken.objects.filter(user=a).values_list("key", flat=True).first() or ""
            lines.append(f"    {a.username}  →  {lib_name}")
            lines.append(f"      {token}")

        lines += [
            "",
            "  Quick API check:",
            "    TOKEN=<paste token above>",
            "    curl -s http://localhost:8000/api/reservations \\",
            '      -H "Authorization: Bearer $TOKEN"',
            sep,
        ]
        self.stdout.write("\n".join(lines))
