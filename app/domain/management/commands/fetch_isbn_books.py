"""
Management command: fetch_isbn_books

Fetches and synchronises books from the e-ISBN ONIX 3.0 XML API.

Usage:
    python manage.py fetch_isbn_books
    python manage.py fetch_isbn_books --limit 200
    python manage.py fetch_isbn_books --limit 50 --batch-size 25
    python manage.py fetch_isbn_books --limit 50 --dry-run
    python manage.py fetch_isbn_books --limit 50 --no-verify-ssl   # local dev only
"""
from __future__ import annotations

import random
import re
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element

try:
    import certifi
    _CERTIFI_CAFILE: str | None = certifi.where()
except ImportError:
    _CERTIFI_CAFILE = None

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from app.domain.isbn import normalise_isbn, validate_isbn
from app.domain.models import Author, Book, BookAuthor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ONIX_NS = "http://ns.editeur.org/onix/3.0/reference"
EISBN_NS = "http://e-isbn.pl"
API_BASE = "https://e-isbn.pl/IsbnWeb/api.xml"
DEFAULT_BATCH_SIZE = 50
DEFAULT_LIMIT = 100
BOOK_CATEGORY_MAX_LENGTH = 511

# Map ONIX ProductForm codes to readable format strings stored in print_type.
FORMAT_MAP: dict[str, str] = {
    "BA": "HARDCOVER",
    "BC": "PAPERBACK",
    "BF": "PAPERBACK",
    "EB": "EBOOK",
}


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _tag(name: str) -> str:
    """Return a fully-qualified ONIX tag name."""
    return f"{{{ONIX_NS}}}{name}"


def _text(parent: Element, child_tag: str) -> str:
    """Return stripped text of a child element, or ''."""
    el = parent.find(_tag(child_tag))
    return (el.text or "").strip() if el is not None else ""


def _next_page_url(root: Element) -> str | None:
    """Return the API pagination cursor for the next page, if present."""
    return root.attrib.get(f"{{{EISBN_NS}}}nextPage")


def _build_page_url(batch_size: int, id_from: int | None = None) -> str:
    """Build an API URL for the optional record cursor and batch size."""
    if id_from is None:
        return f"{API_BASE}?max={batch_size}"
    return f"{API_BASE}?idFrom={id_from}&max={batch_size}"


def _extract_id_from_url(url: str | None) -> int | None:
    """Extract numeric idFrom cursor from an API URL."""
    if not url:
        return None
    match = re.search(r"[?&]idFrom=(\d+)", url)
    if not match:
        return None
    return int(match.group(1))


def _page_signature(page_data: list[dict], next_url: str | None) -> str | None:
    """Return a stable page signature to deduplicate pages reached via different URLs."""
    if not page_data:
        return None
    first_isbn = page_data[0]["isbn"]
    last_isbn = page_data[-1]["isbn"]
    return next_url or f"{first_isbn}:{last_isbn}:{len(page_data)}"


def _normalise_whitespace(value: str) -> str:
    """Collapse repeated whitespace and strip separator noise."""
    return re.sub(r"\s+", " ", value).strip(" ,;/")


def _capitalise_compound_word(value: str) -> str:
    """Apply capitalisation to word fragments while preserving separators."""
    parts = re.split(r"([\-'.’/])", value)
    return "".join(part.capitalize() if part and part not in "-'.’/" else part for part in parts)


def _normalise_capitalisation(value: str) -> str:
    """Normalise text to a capitalised multi-word representation."""
    collapsed = _normalise_whitespace(value)
    if not collapsed:
        return ""
    return " ".join(_capitalise_compound_word(word) for word in collapsed.split(" "))


# ---------------------------------------------------------------------------
# Author normalisation
# ---------------------------------------------------------------------------

def _invert_name(raw: str) -> str:
    """
    Convert inverted author name to natural order.

    'Rymar, Edward'  →  'Edward Rymar'
    'Edward Rymar'   →  'Edward Rymar'  (already natural, left as-is)
    """
    if "," in raw:
        last, _, first = raw.partition(",")
        return f"{first.strip()} {last.strip()}"
    return raw


def _split_possible_joined_names(value: str) -> list[str]:
    """Split obviously concatenated natural-order names into author-sized chunks."""
    tokens = value.split()
    if (
        len(tokens) >= 4
        and len(tokens) % 2 == 0
        and all(token[:1].isalpha() and token[:1].isupper() for token in tokens)
    ):
        return [" ".join(tokens[index:index + 2]) for index in range(0, len(tokens), 2)]
    return [value]


def _looks_like_name_list(parts: list[str]) -> bool:
    """Detect comma-separated natural-order names instead of a single inverted name."""
    natural_name_count = sum(1 for part in parts if len(part.split()) >= 2)
    return natural_name_count >= max(2, len(parts) // 2)


def _normalise_author_name(value: str) -> str:
    """Apply stable capitalisation to an author name."""
    return _normalise_capitalisation(value)


def _extract_author_names(raw_value: str, *, inverted: bool) -> list[str]:
    """Parse one ONIX contributor field into one or more normalised author names."""
    raw_value = _normalise_whitespace(raw_value)
    if not raw_value:
        return []

    if ";" in raw_value:
        chunks = [part.strip() for part in raw_value.split(";") if part.strip()]
    elif "," in raw_value:
        comma_parts = [part.strip() for part in raw_value.split(",") if part.strip()]
        if len(comma_parts) == 2 and inverted:
            chunks = [_invert_name(raw_value)]
        elif len(comma_parts) > 2 and _looks_like_name_list(comma_parts):
            chunks = comma_parts
        elif len(comma_parts) > 2 and len(comma_parts) % 2 == 0:
            chunks = [
                f"{comma_parts[index + 1]} {comma_parts[index]}"
                for index in range(0, len(comma_parts), 2)
            ]
        else:
            chunks = comma_parts
    else:
        chunks = [_invert_name(raw_value) if inverted else raw_value]

    authors: list[str] = []
    for chunk in chunks:
        for candidate in _split_possible_joined_names(chunk):
            normalised = _normalise_author_name(candidate)
            if normalised and normalised not in authors:
                authors.append(normalised)
    return authors


def _extract_contributor_authors(contrib: Element) -> list[str]:
    """Extract author names from a contributor node using the best available fields."""
    names_before_key = _text(contrib, "NamesBeforeKey")
    key_names = _text(contrib, "KeyNames")
    if names_before_key or key_names:
        full_name = f"{names_before_key} {key_names}".strip()
        return _extract_author_names(full_name, inverted=False)

    person_name = _text(contrib, "PersonName")
    if person_name:
        return _extract_author_names(person_name, inverted=False)

    person_name_inverted = _text(contrib, "PersonNameInverted")
    if person_name_inverted:
        return _extract_author_names(person_name_inverted, inverted=True)

    return []


def _is_author_contributor(contrib: Element) -> bool:
    """Return True when the contributor has author role A01."""
    return any(
        (role.text or "").strip() == "A01"
        for role in contrib.findall(_tag("ContributorRole"))
    )


def _normalise_publisher_name(value: str | None) -> str | None:
    """Apply the requested word capitalisation to publisher names."""
    if not value:
        return None
    normalised = _normalise_capitalisation(value)
    return normalised or None


def _extract_language_code(descriptive: Element | None) -> str | None:
    """Extract ONIX language code, preferring the language of the text."""
    if descriptive is None:
        return None

    fallback: str | None = None
    for lang in descriptive.findall(_tag("Language")):
        code = _text(lang, "LanguageCode")
        if not code:
            continue
        language_role = _text(lang, "LanguageRole")
        if language_role == "01":
            return code.lower()
        if fallback is None:
            fallback = code.lower()
    return fallback


def _find_or_create_author(name: str) -> Author:
    """
    Resolve an author by name.

    Looks for an exact match AND the reversed word order (first-last vs
    last-first without comma). If neither exists, creates a new record.
    This prevents duplicate Author rows caused by inconsistent orderings
    across different import runs.
    """
    name = _normalise_author_name(name)
    parts = name.split(" ", 1)
    reversed_name = f"{parts[1]} {parts[0]}" if len(parts) == 2 else name

    author = Author.objects.filter(name__iexact=name).first()
    if author:
        if author.name != name:
            author.name = name
            author.save(update_fields=["name"])
        return author

    author = Author.objects.filter(name__iexact=reversed_name).first()
    if author:
        if author.name != name:
            author.name = name
            author.save(update_fields=["name"])
        return author

    return Author.objects.create(name=name)


# ---------------------------------------------------------------------------
# ONIX product parser
# ---------------------------------------------------------------------------

def _parse_product(product: Element) -> dict | None:
    """
    Parse a single ONIX <Product> element into a normalised dict.

    Returns None if the record is missing mandatory fields (ISBN or title).
    """
    # ── ISBN (ProductIDType 15 = ISBN-13) ──────────────────────────────────
    isbn: str | None = None
    for prod_id in product.findall(_tag("ProductIdentifier")):
        if _text(prod_id, "ProductIDType") == "15":
            raw_isbn = _text(prod_id, "IDValue")
            isbn = normalise_isbn(raw_isbn)
            break
    if not isbn:
        return None

    try:
        validate_isbn(isbn)
    except ValidationError:
        return None

    # ── Title + optional Subtitle ──────────────────────────────────────────
    title = ""
    subtitle = ""
    descriptive = product.find(_tag("DescriptiveDetail"))
    if descriptive is not None:
        for td in descriptive.findall(_tag("TitleDetail")):
            if _text(td, "TitleType") == "01":
                te = td.find(_tag("TitleElement"))
                if te is not None:
                    title = _text(te, "TitleText")
                    subtitle = _text(te, "Subtitle")
                break

    full_title = f"{title} {subtitle}".strip() if subtitle else title
    # Strip trailing ISBD punctuation that occasionally appears in raw ONIX data.
    full_title = re.sub(r"[\s/\\:;=]+$", "", full_title).strip()
    if not full_title:
        return None

    # ── Authors (ContributorRole A01 = by author) ─────────────────────────
    authors: list[str] = []
    if descriptive is not None:
        for contrib in descriptive.findall(_tag("Contributor")):
            if _is_author_contributor(contrib):
                for author_name in _extract_contributor_authors(contrib):
                    if author_name not in authors:
                        authors.append(author_name)

    # ── Format ────────────────────────────────────────────────────────────
    print_type: str | None = None
    if descriptive is not None:
        raw_form = _text(descriptive, "ProductForm")
        if raw_form:
            print_type = FORMAT_MAP.get(raw_form, raw_form)

    # ── Page count ────────────────────────────────────────────────────────
    # ExtentType 05 = total numbered pages (most common in Polish ONIX data).
    # Fall back to 00 (main content page count) if 05 is absent.
    page_count: int | None = None
    if descriptive is not None:
        preferred: int | None = None
        fallback: int | None = None
        for ext in descriptive.findall(_tag("Extent")):
            extent_type = _text(ext, "ExtentType")
            raw_val = _text(ext, "ExtentValue")
            if not raw_val:
                continue
            try:
                val = int(raw_val)
            except ValueError:
                continue
            if extent_type == "05":
                preferred = val
            elif extent_type == "00":
                fallback = val
        page_count = preferred if preferred is not None else fallback

    # ── Categories ────────────────────────────────────────────────────────
    categories: list[str] = []
    if descriptive is not None:
        for subj in descriptive.findall(_tag("Subject")):
            code = _text(subj, "SubjectCode")
            if code:
                categories.append(code)

    # ── Publisher + published year ─────────────────────────────────────────
    publisher: str | None = None
    published_year: int | None = None
    pub_detail = product.find(_tag("PublishingDetail"))
    if pub_detail is not None:
        for pub in pub_detail.findall(_tag("Publisher")):
            name = _text(pub, "PublisherName")
            if name:
                publisher = _normalise_publisher_name(name)
                break

        for pd in pub_detail.findall(_tag("PublishingDate")):
            # DateRole 01 = publication date, 02 = sales embargo date
            if _text(pd, "PublishingDateRole") in ("01", "02"):
                date_str = _text(pd, "Date")
                if len(date_str) >= 4:
                    try:
                        published_year = int(date_str[:4])
                        break
                    except ValueError:
                        pass

    language = _extract_language_code(descriptive)

    return {
        "isbn": isbn,
        "title": full_title,
        "authors": authors,
        "publisher": publisher,
        "published_year": published_year,
        "page_count": page_count,
        "language": language,
        "print_type": print_type,
        "category": ", ".join(categories)[:BOOK_CATEGORY_MAX_LENGTH] if categories else None,
        "_category_raw": ", ".join(categories) if categories else None,
    }


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Fetch and synchronise books from the e-ISBN ONIX 3.0 XML API. "
        "Books are identified by ISBN (get_or_create). "
        "Discovered API pages are shuffled for distributed coverage."
    )

    def _load_page(
        self,
        url: str,
        ssl_ctx: ssl.SSLContext,
    ) -> tuple[list[dict], str | None]:
        with urllib.request.urlopen(url, timeout=30, context=ssl_ctx) as resp:
            xml_bytes: bytes = resp.read()

        root = ET.fromstring(xml_bytes)

        page_data: list[dict] = []
        for product in root.findall(_tag("Product")):
            data = _parse_product(product)
            if data:
                page_data.append(data)

        return page_data, _next_page_url(root)

    def _sync_book_authors(self, book: Book, author_names: list[str], isbn: str) -> bool:
        """Synchronise the book-author join table with parsed author names."""
        desired_author_ids: list[int] = []
        for author_name in author_names:
            try:
                author = _find_or_create_author(author_name)
            except Exception as exc:
                self.stderr.write(
                    self.style.WARNING(
                        f"  [WARN   ] {isbn} — author '{author_name}' skipped: {exc}"
                    )
                )
                continue
            desired_author_ids.append(author.id)

        current_author_ids = set(
            BookAuthor.objects.filter(book=book).values_list("author_id", flat=True)
        )
        desired_author_ids_set = set(desired_author_ids)

        removed = BookAuthor.objects.filter(
            book=book,
            author_id__in=current_author_ids - desired_author_ids_set,
        ).delete()[0]

        added = 0
        for author_id in desired_author_ids:
            _, was_created = BookAuthor.objects.get_or_create(book=book, author_id=author_id)
            if was_created:
                added += 1

        return bool(removed or added)

    def _discover_upper_id_bound(
        self,
        batch_size: int,
        ssl_ctx: ssl.SSLContext,
        starting_id: int,
    ) -> int:
        """Estimate the highest idFrom that still yields products."""
        lower_bound = max(starting_id, 1)
        upper_bound = lower_bound

        while True:
            page_data, _ = self._load_page(_build_page_url(batch_size, upper_bound), ssl_ctx)
            if not page_data:
                break
            lower_bound = upper_bound
            upper_bound *= 2
            if upper_bound >= 100_000_000:
                return lower_bound

        while lower_bound + 1 < upper_bound:
            probe_id = (lower_bound + upper_bound) // 2
            page_data, _ = self._load_page(_build_page_url(batch_size, probe_id), ssl_ctx)
            if page_data:
                lower_bound = probe_id
            else:
                upper_bound = probe_id

        return lower_bound

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_LIMIT,
            metavar="N",
            help=(
                "Maximum number of new books to create during this run "
                f"(default: {DEFAULT_LIMIT}). Existing books may still be scanned "
                "and updated while searching for new records."
            ),
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            metavar="N",
            help=(
                f"Records requested per API call (default: {DEFAULT_BATCH_SIZE}). "
                "Larger values mean fewer round-trips but slower per-request."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and print results without writing anything to the database.",
        )
        parser.add_argument(
            "--no-verify-ssl",
            action="store_true",
            help=(
                "Disable SSL certificate verification. "
                "Use only in local dev when the CA chain cannot be resolved "
                "(e.g. Certum CA on Windows). Never use in production."
            ),
        )

    def handle(self, *args, **options):
        limit: int = options["limit"]
        batch_size: int = min(options["batch_size"], 100)  # safety cap
        dry_run: bool = options["dry_run"]
        no_verify_ssl: bool = options["no_verify_ssl"]

        if no_verify_ssl:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            self.stderr.write(
                self.style.WARNING("WARNING: SSL verification disabled (--no-verify-ssl).")
            )
        elif _CERTIFI_CAFILE:
            ssl_ctx = ssl.create_default_context(cafile=_CERTIFI_CAFILE)
        else:
            ssl_ctx = ssl.create_default_context()

        self.stdout.write(
            f"e-ISBN sync  |  limit={limit}  batch_size={batch_size}  dry_run={dry_run}"
        )

        created = 0
        updated = 0
        skipped = 0
        errors = 0
        scanned = 0
        seen_isbns: set[str] = set()
        seen_page_urls: set[str] = set()
        seen_page_signatures: set[str] = set()

        def load_page_once(url: str) -> tuple[list[dict] | None, str | None]:
            nonlocal errors

            if url in seen_page_urls:
                return None, None
            seen_page_urls.add(url)

            try:
                page_data, next_url = self._load_page(url, ssl_ctx)
            except urllib.error.URLError as exc:
                self.stderr.write(f"  Request failed ({url}): {exc.reason}")
                errors += 1
                return None, None
            except OSError as exc:
                self.stderr.write(f"  Request error ({url}): {exc}")
                errors += 1
                return None, None
            except ET.ParseError as exc:
                self.stderr.write(f"  XML parse error ({url}): {exc}")
                errors += 1
                return None, None

            page_key = _page_signature(page_data, next_url)
            if page_key and page_key in seen_page_signatures:
                return None, next_url
            if page_key:
                seen_page_signatures.add(page_key)

            return page_data, next_url

        def process_page(page_data: list[dict]) -> None:
            nonlocal created, updated, skipped, errors, scanned

            for data in page_data:
                if created >= limit:
                    break

                scanned += 1

                isbn = data["isbn"]
                if isbn in seen_isbns:
                    continue
                seen_isbns.add(isbn)

                if dry_run:
                    self.stdout.write(
                        f"  [DRY-RUN] {isbn} — {data['title']}"
                        f" ({data['published_year']}, {data['print_type']})"
                        f"  authors={data['authors']}"
                    )
                    created += 1
                    continue

                raw_cat = data.get("_category_raw") or ""
                if len(raw_cat) > BOOK_CATEGORY_MAX_LENGTH:
                    self.stderr.write(
                        self.style.WARNING(
                            f"  [WARN   ] {isbn} — category too long "
                            f"({len(raw_cat)} chars), truncated to {BOOK_CATEGORY_MAX_LENGTH}.\n"
                            f"             Full value: {raw_cat}"
                        )
                    )

                try:
                    book, was_created = Book.objects.get_or_create(
                        isbn=isbn,
                        defaults={
                            "title": data["title"],
                            "publisher": data["publisher"],
                            "published_year": data["published_year"],
                            "page_count": data["page_count"],
                            "language": data["language"],
                            "print_type": data["print_type"],
                            "category": data["category"],
                            "data_source": "e-isbn",
                            "integration_source": 1,
                        },
                    )
                except Exception as exc:
                    errors += 1
                    self.stderr.write(
                        self.style.ERROR(f"  [ERROR  ] {isbn} — DB save failed: {exc}")
                    )
                    continue

                synced_fields = {
                    "title": data["title"],
                    "publisher": data["publisher"],
                    "published_year": data["published_year"],
                    "page_count": data["page_count"],
                    "language": data["language"],
                    "print_type": data["print_type"],
                    "category": data["category"],
                    "data_source": "e-isbn",
                    "integration_source": 1,
                }
                changed_fields: list[str] = []
                for field_name, field_value in synced_fields.items():
                    if getattr(book, field_name) != field_value:
                        setattr(book, field_name, field_value)
                        changed_fields.append(field_name)

                if changed_fields:
                    book.save(update_fields=changed_fields)

                authors_changed = self._sync_book_authors(book, data["authors"], isbn)

                if was_created:
                    created += 1
                    self.stdout.write(f"  [CREATED] {isbn} — {book.title}")
                elif changed_fields or authors_changed:
                    updated += 1
                    self.stdout.write(f"  [UPDATED] {isbn} — {book.title}")
                else:
                    skipped += 1
                    self.stdout.write(f"  [EXISTS ] {isbn} — {book.title}")

        # The API is cursor-paginated. Sequentially starting from page one biases
        # imports toward one catalog segment, so we probe a wide idFrom range and
        # buffer pages from multiple distant entry points before processing.
        page_probe_limit = max(limit // batch_size + 10, 15)
        next_url: str | None = None
        buffered_pages: list[list[dict]] = []
        frontier_urls: list[str] = []

        first_page_url = _build_page_url(batch_size)
        first_page_data, next_url = load_page_once(first_page_url)
        if next_url:
            frontier_urls.append(next_url)

        first_next_id = _extract_id_from_url(next_url)
        if first_next_id is not None:
            try:
                upper_id_bound = self._discover_upper_id_bound(
                    batch_size,
                    ssl_ctx,
                    first_next_id,
                )
                self.stdout.write(
                    f"Discovered e-ISBN id range up to about {upper_id_bound}."
                )
            except (urllib.error.URLError, OSError, ET.ParseError) as exc:
                upper_id_bound = first_next_id
                self.stderr.write(
                    self.style.WARNING(
                        f"  [WARN   ] Failed to estimate upper id bound precisely: {exc}"
                    )
                )
        else:
            upper_id_bound = None

        if upper_id_bound and upper_id_bound > 1:
            random_seed_ids: set[int] = set()
            max_seed_attempts = page_probe_limit * 6

            while len(buffered_pages) < page_probe_limit and len(random_seed_ids) < max_seed_attempts:
                seed_id = random.randint(1, upper_id_bound)
                if seed_id in random_seed_ids:
                    continue
                random_seed_ids.add(seed_id)

                page_data, discovered_next_url = load_page_once(
                    _build_page_url(batch_size, seed_id)
                )
                if page_data:
                    buffered_pages.append(page_data)
                if discovered_next_url:
                    frontier_urls.append(discovered_next_url)

        if not buffered_pages and first_page_data:
            buffered_pages.append(first_page_data)

        while len(buffered_pages) < page_probe_limit and frontier_urls:
            current_url = frontier_urls.pop(random.randrange(len(frontier_urls)))
            page_data, discovered_next_url = load_page_once(current_url)
            if page_data:
                buffered_pages.append(page_data)
            if discovered_next_url:
                frontier_urls.append(discovered_next_url)

        random.shuffle(buffered_pages)

        for page_data in buffered_pages:
            process_page(page_data)
            if created >= limit:
                break

        while created < limit and frontier_urls:
            current_url = frontier_urls.pop(random.randrange(len(frontier_urls)))
            page_data, discovered_next_url = load_page_once(current_url)
            if page_data:
                process_page(page_data)
            if discovered_next_url:
                frontier_urls.append(discovered_next_url)

        if dry_run:
            summary = (
                f"\nDone. DRY-RUN would create: {created}  |  "
                f"Scanned: {scanned}  |  Errors: {errors}"
            )
        else:
            summary = (
                f"\nDone. Created: {created}  |  Updated: {updated}  |  "
                f"Exists/skipped: {skipped}  |  Scanned: {scanned}  |  Errors: {errors}"
            )
        self.stdout.write(self.style.SUCCESS(summary))
