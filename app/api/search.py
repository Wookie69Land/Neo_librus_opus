from __future__ import annotations

from datetime import datetime

from django.db.models import Q, QuerySet
from ninja import Query, Router, Schema
from ninja.errors import HttpError

from app.api.serializers import AuthorSchemaOut
from app.domain.languages import get_language_display
from app.domain.isbn import normalise_isbn
from app.domain.models import Book, LibraryBook

router = Router(tags=["Search"])


class SearchLibraryInfoSchema(Schema):
    id: int
    name: str
    city: str | None = None
    region: int | None = None
    is_available: bool


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
    libraries: list[SearchLibraryInfoSchema]


class SimpleBookSearchQuery(Schema):
    q: str


class AdvancedBookSearchQuery(Schema):
    id: int | None = None
    title: str | None = None
    isbn: str | None = None
    integration_source: int | None = None
    data_source: str | None = None
    google_id: str | None = None
    publisher: str | None = None
    published_year: int | None = None
    published_year_min: int | None = None
    published_year_max: int | None = None
    description: str | None = None
    page_count: int | None = None
    page_count_min: int | None = None
    page_count_max: int | None = None
    print_type: str | None = None
    category: str | None = None
    cover_url: str | None = None
    language: str | None = None
    author_id: int | None = None
    author_name: str | None = None
    library_id: int | None = None
    library_name: str | None = None
    library_city: str | None = None
    library_region: int | None = None
    is_available: bool | None = None


async def _serialize_book(book: Book) -> BookSearchResultSchema:
    authors = [
        AuthorSchemaOut(id=author.id, name=author.name)
        async for author in book.authors.all().order_by("name")
    ]
    libraries = [
        SearchLibraryInfoSchema(
            id=library_book.library.id,
            name=library_book.library.name,
            city=library_book.library.city,
            region=library_book.library.region,
            is_available=library_book.is_available,
        )
        async for library_book in LibraryBook.objects.select_related("library")
        .filter(book_id=book.id)
        .order_by("library__name")
    ]

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
    return Book.objects.all().distinct().order_by("title", "id")


@router.get("/books", response=list[BookSearchResultSchema], auth=None)
async def search_books(request, params: SimpleBookSearchQuery = Query(...)):
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
    return [_serialize async for _serialize in _serialized_books(books)]


@router.get("/books/advanced", response=list[BookSearchResultSchema])
async def advanced_search_books(request, params: AdvancedBookSearchQuery = Query(...)):
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
    if params.author_id is not None:
        books = books.filter(authors__id=params.author_id)
    if params.author_name:
        books = books.filter(authors__name__icontains=params.author_name.strip())
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

    return [_serialize async for _serialize in _serialized_books(books)]


async def _serialized_books(books: QuerySet[Book]):
    async for book in books:
        yield await _serialize_book(book)