
from ninja import Router

from app.api.serializers import AuthorSchemaOut, BookSchemaIn, BookSchemaOut
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
            publication_date=book.publication_date,
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
    book = await book_repo.create(**payload.dict(exclude={"author_ids"}))
    for author_id in payload.author_ids:
        await book_author_repo.model.objects.acreate(book=book, author_id=author_id)

    authors = [await author_repo.get_by_id(author_id) for author_id in payload.author_ids]
    return BookSchemaOut(
        id=book.id,
        title=book.title,
        isbn=book.isbn,
        publisher=book.publisher,
        publication_date=book.publication_date,
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
        publication_date=book.publication_date,
        page_count=book.page_count,
        cover_url=book.cover_url,
        language=book.language,
        authors=[
            AuthorSchemaOut(**author.__dict__) async for author in book.authors.all()
        ]
    )

@router.put("/{book_id}", response=BookSchemaOut)
async def update_book(request, book_id: int, payload: BookSchemaIn):
    book = await book_repo.update(book_id, **payload.dict(exclude={"author_ids"}))
    await BookAuthor.objects.filter(book_id=book_id).adelete()
    for author_id in payload.author_ids:
        await book_author_repo.model.objects.acreate(book=book, author_id=author_id)

    authors = [await author_repo.get_by_id(author_id) for author_id in payload.author_ids]
    return BookSchemaOut(
        id=book.id,
        title=book.title,
        isbn=book.isbn,
        publisher=book.publisher,
        publication_date=book.publication_date,
        page_count=book.page_count,
        cover_url=book.cover_url,
        language=book.language,
        authors=authors
    )

@router.delete("/{book_id}")
async def delete_book(request, book_id: int):
    await book_repo.delete(book_id)
    return {"success": True}
