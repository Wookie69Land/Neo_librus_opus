
from django.core.exceptions import ValidationError
from django.db.models import Case, IntegerField, Q, Value, When
from ninja import Query, Router, Schema
from ninja.errors import HttpError

from app.api.book_availability import (
    MOCK_AVAILABILITY_SOURCE,
    get_book_library_availability,
    get_request_user_region,
)
from app.api.permissions import require_library_admin_or_superuser
from app.api.serializers import (
    AuthorSchemaOut,
    BookAvailabilityResponseSchema,
    BookDetailSchemaOut,
    BookLanguageSchema,
    BookSchemaIn,
    BookSchemaOut,
    PaginatedBookSchemaOut,
)
from app.domain.isbn import normalise_isbn, validate_isbn
from app.domain.models import Author, Book, BookAuthor
from app.domain.languages import get_language_display, normalize_language_code
from app.domain.repositories import AuthorRepository, BookAuthorRepository, BookRepository

router = Router(tags=["Books"])
book_repo = BookRepository(Book)
author_repo = AuthorRepository(Author)
book_author_repo = BookAuthorRepository(BookAuthor)


class BookListQuery(Schema):
    page: int = 1
    page_size: int = 12
    library_id: int | None = None


async def _serialize_book(book: Book) -> BookSchemaOut:
    authors = [
        AuthorSchemaOut(id=author.id, name=author.name)
        async for author in book.authors.all().order_by("name")
    ]
    return BookSchemaOut.from_book(book, authors)


async def _serialize_book_detail(request, book: Book) -> BookDetailSchemaOut:
    base_book = await _serialize_book(book)
    user_region = await get_request_user_region(request)
    libraries = await get_book_library_availability(book.id, user_region=user_region)
    return BookDetailSchemaOut(**base_book.model_dump(), libraries=libraries)


def _ordered_books_queryset():
    return Book.objects.annotate(
        has_cover=Case(
            When(Q(cover_url__isnull=False) & ~Q(cover_url=""), then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    ).prefetch_related("authors").order_by("-has_cover", "-id")


@router.get(
    "",
    response=PaginatedBookSchemaOut,
    auth=None,
    summary="List books",
    description=(
        "Return paginated books ordered with records that have a cover first. "
        "This endpoint is public; if a Bearer token is provided, it is ignored for the list response."
    ),
)
async def list_books(request, params: BookListQuery = Query(...)):
    """Return a paginated list of books."""

    page = max(params.page, 1)
    page_size = min(max(params.page_size, 1), 100)

    books = _ordered_books_queryset()
    if params.library_id is not None:
        books = books.filter(librarybook__library_id=params.library_id)
    total = await books.acount()
    start = (page - 1) * page_size
    end = start + page_size

    items = [serialized async for serialized in _serialized_books(books[start:end])]
    total_pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedBookSchemaOut(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/languages",
    response=list[BookLanguageSchema],
    summary="List supported book languages",
    description="Return distinct normalized language codes currently used by stored books.",
)
async def list_book_languages(request):
    """Return language codes derived from existing book records."""

    unique_codes: set[str] = set()
    async for language in Book.objects.exclude(language__isnull=True).exclude(language="").values_list(
        "language", flat=True
    ).distinct():
        normalized = normalize_language_code(language)
        if normalized:
            unique_codes.add(normalized)

    return [
        BookLanguageSchema(code=code, display=get_language_display(code) or code.upper())
        for code in sorted(unique_codes, key=lambda item: get_language_display(item) or item)
    ]


@router.post(
    "",
    response={200: BookSchemaOut, 422: dict, 403: dict},
    summary="Create book",
    description="Create a book and attach the provided authors. Library admin or superuser role required.",
)
async def create_book(request, payload: BookSchemaIn):
    """Create a new book and its author relations."""

    await require_library_admin_or_superuser(request)
    payload_data = payload.dict(exclude={"author_ids"})
    try:
        validate_isbn(payload_data["isbn"])
        payload_data["isbn"] = normalise_isbn(payload_data["isbn"])
        book = await book_repo.create(**payload_data)
    except ValidationError as exc:
        raise HttpError(422, "; ".join(exc.messages)) from exc

    for author_id in payload.author_ids:
        await book_author_repo.model.objects.acreate(book=book, author_id=author_id)

    return await _serialize_book(book)

@router.get(
    "/{book_id}",
    response={200: BookDetailSchemaOut, 404: dict},
    auth=None,
    summary="Get book details",
    description=(
        "Return a single book with per-library availability. "
        "If a Bearer token is supplied, libraries from the user's region are listed first."
    ),
)
async def get_book(request, book_id: int):
    """Return one book enriched with current library availability."""

    book = await book_repo.get_by_id(book_id)
    if book is None:
        raise HttpError(404, "Book not found.")

    return await _serialize_book_detail(request, book)


@router.get(
    "/{book_id}/availability",
    response={200: BookAvailabilityResponseSchema, 404: dict},
    auth=None,
    summary="Get book availability",
    description=(
        "Return live availability information for one book across libraries. "
        "If a Bearer token is supplied, libraries matching the user's region are prioritized."
    ),
)
async def get_book_availability(request, book_id: int):
    """Return availability details for a single book across libraries."""

    book = await book_repo.get_by_id(book_id)
    if book is None:
        raise HttpError(404, "Book not found.")

    user_region = await get_request_user_region(request)
    libraries = await get_book_library_availability(book.id, user_region=user_region)
    return BookAvailabilityResponseSchema(
        book_id=book.id,
        title=book.title,
        user_region=user_region,
        checked_via=MOCK_AVAILABILITY_SOURCE,
        libraries=libraries,
    )

@router.put(
    "/{book_id}",
    response={200: BookSchemaOut, 404: dict, 422: dict, 403: dict},
    summary="Update book",
    description="Update a book and replace its author relations. Library admin or superuser role required.",
)
async def update_book(request, book_id: int, payload: BookSchemaIn):
    """Update a book and refresh its author assignments."""

    await require_library_admin_or_superuser(request)
    payload_data = payload.dict(exclude={"author_ids"})
    try:
        validate_isbn(payload_data["isbn"])
        payload_data["isbn"] = normalise_isbn(payload_data["isbn"])
        book = await book_repo.update(book_id, **payload_data)
    except ValidationError as exc:
        raise HttpError(422, "; ".join(exc.messages)) from exc

    if book is None:
        raise HttpError(404, "Book not found.")

    await BookAuthor.objects.filter(book_id=book_id).adelete()
    for author_id in payload.author_ids:
        await book_author_repo.model.objects.acreate(book=book, author_id=author_id)

    return await _serialize_book(book)

@router.delete(
    "/{book_id}",
    summary="Delete book",
    description="Delete a book by identifier. Library admin or superuser role required.",
)
async def delete_book(request, book_id: int):
    """Delete a book."""

    await require_library_admin_or_superuser(request)
    await book_repo.delete(book_id)
    return {"success": True}


async def _serialized_books(books):
    async for book in books:
        yield await _serialize_book(book)
