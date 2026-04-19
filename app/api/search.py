from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db.models import Prefetch, Q, QuerySet
from ninja import Field, Query, Router, Schema
from ninja.errors import HttpError
from pydantic import field_validator

from app.api.book_availability import get_prefetched_book_library_availability, get_request_user_region
from app.api.serializers import AuthorSchemaOut, BookLibraryAvailabilitySchema
from app.domain.languages import get_language_display, normalize_language_code
from app.domain.isbn import normalise_isbn
from app.domain.models import Author, Book, LibraryBook

router = Router(tags=["Search"])


class BookSearchResultSchema(Schema):
    id: int
    title: str
    isbn: str
    integration_source: int
    data_source: str | None = None
    google_id: str | None = None
    publisher: str | None = None
    published_year: int | None = None
    description: str | None = None
    page_count: int | None = None
    print_type: str | None = None
    category: str | None = None
    cover_url: str | None = None
    language: str | None = None
    language_display: str | None = None
    last_updated: datetime
    authors: list[AuthorSchemaOut]
    libraries: list[BookLibraryAvailabilitySchema] = Field(
        ..., description="Libraries holding the book, ordered by user region when available."
    )


class SimpleBookSearchQuery(Schema):
    q: str = Field(..., description="Free-text query matched against title, category, publisher, authors, and ISBN.")
    page: int = Field(1, description="Page number, starting from 1.")
    page_size: int = Field(20, description="Number of results per page. Maximum 100.")


class AdvancedBookSearchQuery(Schema):
    id: int | None = Field(None, description="Exact book identifier.")
    title: str | None = Field(None, description="Substring match on title.")
    isbn: str | None = Field(None, description="ISBN fragment or full ISBN; normalized before filtering.")
    integration_source: int | None = Field(None, description="Exact integration source code.")
    data_source: str | None = Field(None, description="Substring match on data source.")
    google_id: str | None = Field(None, description="Substring match on Google Books identifier.")
    publisher: str | None = Field(None, description="Substring match on publisher.")
    published_year: int | None = Field(None, description="Exact publication year.")
    published_year_min: int | None = Field(None, description="Minimum publication year, inclusive.")
    published_year_max: int | None = Field(None, description="Maximum publication year, inclusive.")
    description: str | None = Field(None, description="Substring match on description.")
    page_count: int | None = Field(None, description="Exact page count.")
    page_count_min: int | None = Field(None, description="Minimum page count, inclusive.")
    page_count_max: int | None = Field(None, description="Maximum page count, inclusive.")
    print_type: str | None = Field(None, description="Substring match on print type.")
    category: str | None = Field(None, description="Substring match on category.")
    cover_url: str | None = Field(None, description="Substring match on cover URL.")
    language: str | None = Field(None, description="Substring match on language code.")
    languages: list[str] | None = Field(
        None,
        description="Repeat the parameter or pass comma-separated values to match multiple language codes.",
    )
    author_id: int | None = Field(None, description="Exact author identifier.")
    author_ids: list[int] | None = Field(
        None,
        description="Repeat the parameter or pass comma-separated values to match any of multiple author IDs.",
    )
    author_name: str | None = Field(None, description="Substring match on author name.")
    author_names: list[str] | None = Field(
        None,
        description="Repeat the parameter or pass comma-separated values to match any of multiple author names.",
    )
    library_id: int | None = Field(None, description="Only books linked to the given library.")
    library_name: str | None = Field(None, description="Substring match on linked library name.")
    library_city: str | None = Field(None, description="Substring match on linked library city.")
    library_region: int | None = Field(None, description="Only books linked to libraries in the given region.")
    is_available: bool | None = Field(None, description="Filter by current library-book availability flag.")
    page: int = Field(1, description="Page number, starting from 1.")
    page_size: int = Field(20, description="Number of results per page. Maximum 100.")

    @field_validator("languages", "author_names", mode="before")
    @classmethod
    def normalize_multi_string_filters(cls, value: Any) -> list[str] | None:
        return _normalize_multi_string_values(value)

    @field_validator("author_ids", mode="before")
    @classmethod
    def normalize_multi_int_filters(cls, value: Any) -> list[int] | None:
        values = _normalize_multi_string_values(value)
        if values is None:
            return None
        return [int(item) for item in values]


def _normalize_multi_string_values(value: Any) -> list[str] | None:
    if value is None:
        return None

    raw_values = value if isinstance(value, list) else [value]
    normalized_values: list[str] = []
    for raw_value in raw_values:
        if raw_value is None:
            continue
        for item in str(raw_value).split(","):
            normalized = item.strip()
            if normalized:
                normalized_values.append(normalized)

    return normalized_values or None


class PaginatedBookSearchSchema(Schema):
    items: list[BookSearchResultSchema]
    page: int
    page_size: int
    total: int
    total_pages: int


def _get_prefetched_related_objects(book: Book, relation_name: str):
    return getattr(book, "_prefetched_objects_cache", {}).get(relation_name, [])


async def _serialize_book(book: Book, *, user_region: int | None) -> BookSearchResultSchema:
    authors = [
        AuthorSchemaOut(id=author.id, name=author.name)
        for author in _get_prefetched_related_objects(book, "authors")
    ]
    libraries = await get_prefetched_book_library_availability(
        _get_prefetched_related_objects(book, "librarybook_set"),
        user_region=user_region,
    )

    return BookSearchResultSchema(
        id=book.id,
        title=book.title,
        isbn=book.isbn,
        integration_source=book.integration_source,
        data_source=book.data_source,
        google_id=book.google_id,
        publisher=book.publisher,
        published_year=book.published_year,
        description=book.description,
        page_count=book.page_count,
        print_type=book.print_type,
        category=book.category,
        cover_url=book.cover_url,
        language=book.language,
        language_display=get_language_display(book.language),
        last_updated=book.last_updated,
        authors=authors,
        libraries=libraries,
    )


def _base_search_queryset() -> QuerySet[Book]:
    return Book.objects.all().order_by("title", "id")


def _search_prefetches() -> tuple[Prefetch, Prefetch]:
    return (
        Prefetch("authors", queryset=Author.objects.order_by("name")),
        Prefetch("librarybook_set", queryset=LibraryBook.objects.select_related("library", "book")),
    )


async def _paginate_search_results(
    books: QuerySet[Book],
    *,
    page: int,
    page_size: int,
    user_region: int | None,
) -> PaginatedBookSearchSchema:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    distinct_books = books.distinct()
    total = await distinct_books.acount()
    start = (page - 1) * page_size
    end = start + page_size

    paginated_books = [
        book
        async for book in distinct_books.prefetch_related(*_search_prefetches())[start:end]
    ]
    items = [await _serialize_book(book, user_region=user_region) for book in paginated_books]
    total_pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedBookSearchSchema(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/books",
    response={200: PaginatedBookSearchSchema, 422: dict},
    auth=None,
    summary="Search books",
    description=(
        "Run a paginated free-text search across titles, categories, publishers, authors, and ISBNs. "
        "If a Bearer token is supplied, matching-region libraries are shown first in each result."
    ),
)
async def search_books(request, params: SimpleBookSearchQuery = Query(...)):
    """Return books matching a free-text query."""

    query = params.q.strip()
    if not query:
        raise HttpError(422, "Query string cannot be empty.")

    normalized_isbn = normalise_isbn(query)
    predicates = (
        Q(title__icontains=query)
        | Q(category__icontains=query)
        | Q(publisher__icontains=query)
        | Q(authors__name__icontains=query)
    )
    if normalized_isbn:
        predicates |= Q(isbn__icontains=normalized_isbn)

    books = _base_search_queryset().filter(predicates)
    user_region = await get_request_user_region(request)
    return await _paginate_search_results(
        books,
        page=params.page,
        page_size=params.page_size,
        user_region=user_region,
    )


@router.get(
    "/books/advanced",
    response=PaginatedBookSearchSchema,
    summary="Advanced book search",
    description=(
        "Filter books using detailed metadata, author, and library criteria with paginated results. "
        "Use a Bearer token in the Authorization header. "
        "Multi-value filters can be sent as repeated query parameters or comma-separated values. "
        "Authenticated access is required because this route uses the API-wide Bearer auth.\n\n"
        "Example with repeated query parameters:\n"
        "```bash\n"
        "curl -G https://librarius-api.nanys.pl/api/search/books/advanced \\\n"
        "  -H \"Authorization: Bearer <signed_jwt_token>\" \\\n"
        "  --data-urlencode \"languages=eng\" \\\n"
        "  --data-urlencode \"languages=pol\" \\\n"
        "  --data-urlencode \"author_names=Adam Mickiewicz\" \\\n"
        "  --data-urlencode \"author_names=Witold Gombrowicz\" \\\n"
        "  --data-urlencode \"library_city=Warszawa\" \\\n"
        "  --data-urlencode \"is_available=true\"\n"
        "```\n\n"
        "Example with comma-separated multi-value filters:\n"
        "```bash\n"
        "curl -G https://librarius-api.nanys.pl/api/search/books/advanced \\\n"
        "  -H \"Authorization: Bearer <signed_jwt_token>\" \\\n"
        "  --data-urlencode \"author_ids=12,18\" \\\n"
        "  --data-urlencode \"languages=eng,pol\" \\\n"
        "  --data-urlencode \"library_region=7\"\n"
        "```"
    ),
)
async def advanced_search_books(request, params: AdvancedBookSearchQuery = Query(...)):
    """Return books matching advanced filter parameters."""

    books = _base_search_queryset()

    if params.id is not None:
        books = books.filter(id=params.id)
    if params.title:
        books = books.filter(title__icontains=params.title.strip())
    if params.isbn:
        books = books.filter(isbn__icontains=normalise_isbn(params.isbn))
    if params.integration_source is not None:
        books = books.filter(integration_source=params.integration_source)
    if params.data_source:
        books = books.filter(data_source__icontains=params.data_source.strip())
    if params.google_id:
        books = books.filter(google_id__icontains=params.google_id.strip())
    if params.publisher:
        books = books.filter(publisher__icontains=params.publisher.strip())
    if params.published_year is not None:
        books = books.filter(published_year=params.published_year)
    if params.published_year_min is not None:
        books = books.filter(published_year__gte=params.published_year_min)
    if params.published_year_max is not None:
        books = books.filter(published_year__lte=params.published_year_max)
    if params.description:
        books = books.filter(description__icontains=params.description.strip())
    if params.page_count is not None:
        books = books.filter(page_count=params.page_count)
    if params.page_count_min is not None:
        books = books.filter(page_count__gte=params.page_count_min)
    if params.page_count_max is not None:
        books = books.filter(page_count__lte=params.page_count_max)
    if params.print_type:
        books = books.filter(print_type__icontains=params.print_type.strip())
    if params.category:
        books = books.filter(category__icontains=params.category.strip())
    if params.cover_url:
        books = books.filter(cover_url__icontains=params.cover_url.strip())
    if params.language:
        books = books.filter(language__icontains=params.language.strip())
    if params.languages:
        language_filters = Q()
        for language in params.languages:
            normalized_language = normalize_language_code(language)
            if normalized_language:
                language_filters |= Q(language__icontains=normalized_language)
        if language_filters:
            books = books.filter(language_filters)
    if params.author_id is not None:
        books = books.filter(authors__id=params.author_id)
    if params.author_ids:
        books = books.filter(authors__id__in=params.author_ids)
    if params.author_name:
        books = books.filter(authors__name__icontains=params.author_name.strip())
    if params.author_names:
        author_name_filters = Q()
        for author_name in params.author_names:
            author_name_filters |= Q(authors__name__icontains=author_name)
        books = books.filter(author_name_filters)
    if params.library_id is not None:
        books = books.filter(librarybook__library_id=params.library_id)
    if params.library_name:
        books = books.filter(librarybook__library__name__icontains=params.library_name.strip())
    if params.library_city:
        books = books.filter(librarybook__library__city__icontains=params.library_city.strip())
    if params.library_region is not None:
        books = books.filter(librarybook__library__region=params.library_region)
    if params.is_available is not None:
        books = books.filter(librarybook__is_available=params.is_available)

    user_region = await get_request_user_region(request)
    return await _paginate_search_results(
        books,
        page=params.page,
        page_size=params.page_size,
        user_region=user_region,
    )