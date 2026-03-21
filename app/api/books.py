
from django.core.exceptions import ValidationError
from ninja import Router
from ninja.errors import HttpError

from app.api.serializers import AuthorSchemaOut, BookSchemaIn, BookSchemaOut
from app.domain.isbn import normalise_isbn, validate_isbn
from app.domain.models import Author, Book, BookAuthor
from app.domain.repositories import AuthorRepository, BookAuthorRepository, BookRepository

router = Router(tags=["Books"])
book_repo = BookRepository(Book)
author_repo = AuthorRepository(Author)
book_author_repo = BookAuthorRepository(BookAuthor)

@router.get("", response=list[BookSchemaOut])
async def list_books(request):
    books = await book_repo.get_all()
    return [
        BookSchemaOut(
            id=book.id,
            title=book.title,
            isbn=book.isbn,
            publisher=book.publisher,
            published_year=book.published_year,
            page_count=book.page_count,
            cover_url=book.cover_url,
            language=book.language,
            authors=[
                AuthorSchemaOut(**author.__dict__) async for author in book.authors.all()
            ],
        )
        for book in books
    ]


@router.post("", response=BookSchemaOut)
async def create_book(request, payload: BookSchemaIn):
    payload_data = payload.dict(exclude={"author_ids"})
    try:
        validate_isbn(payload_data["isbn"])
        payload_data["isbn"] = normalise_isbn(payload_data["isbn"])
        book = await book_repo.create(**payload_data)
    except ValidationError as exc:
        raise HttpError(422, "; ".join(exc.messages)) from exc

    for author_id in payload.author_ids:
        await book_author_repo.model.objects.acreate(book=book, author_id=author_id)

    authors = [await author_repo.get_by_id(author_id) for author_id in payload.author_ids]
    return BookSchemaOut(
        id=book.id,
        title=book.title,
        isbn=book.isbn,
        publisher=book.publisher,
        published_year=book.published_year,
        page_count=book.page_count,
        cover_url=book.cover_url,
        language=book.language,
        authors=authors
    )

@router.get("/{book_id}", response=BookSchemaOut)
async def get_book(request, book_id: int):
    book = await book_repo.get_by_id(book_id)
    return BookSchemaOut(
        id=book.id,
        title=book.title,
        isbn=book.isbn,
        publisher=book.publisher,
        published_year=book.published_year,
        page_count=book.page_count,
        cover_url=book.cover_url,
        language=book.language,
        authors=[
            AuthorSchemaOut(**author.__dict__) async for author in book.authors.all()
        ]
    )

@router.put("/{book_id}", response=BookSchemaOut)
async def update_book(request, book_id: int, payload: BookSchemaIn):
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

    authors = [await author_repo.get_by_id(author_id) for author_id in payload.author_ids]
    return BookSchemaOut(
        id=book.id,
        title=book.title,
        isbn=book.isbn,
        publisher=book.publisher,
        published_year=book.published_year,
        page_count=book.page_count,
        cover_url=book.cover_url,
        language=book.language,
        authors=authors
    )

@router.delete("/{book_id}")
async def delete_book(request, book_id: int):
    await book_repo.delete(book_id)
    return {"success": True}
