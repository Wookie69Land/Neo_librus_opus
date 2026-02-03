"""Books API router with CRUD endpoints and permission dependencies.

All database access is performed through the async repository layer to
adhere to the project's async-first rules.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List

from django.core.exceptions import PermissionDenied
from ninja import Router, Schema
from ninja.security import HttpBearer

from app.api.api import api
from app.domain.models import Book
from app.domain.repository import AsyncRepository


class BookOut(Schema):
    """Output schema for a Book resource."""

    id: int
    title: str
    author: str
    isbn: str | None
    copies: int
    created_at: datetime
    updated_at: datetime


class BookIn(Schema):
    """Input/validation schema for creating/updating a Book."""

    title: str
    author: str
    isbn: str | None = None
    copies: int = 1


class HasPerm:  # pragma: no cover - trivial security wrapper
    """Ninja dependency that requires specific Django permissions.

    Usage:
        Depends(HasPerm(["domain.add_book"]))
    """

    def __init__(self, perm_codenames: list[str]) -> None:
        self.perm_codenames = perm_codenames

    def __call__(self, request: Any) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionDenied("Authentication required")
        if not user.has_perms(self.perm_codenames):
            raise PermissionDenied("Insufficient permissions")
        return True


router = Router(tags=["Books"])
repo = AsyncRepository(Book)


@router.get("/books", response=List[BookOut], summary="List books", description="Returns all books.")
async def list_books(request: Any) -> List[BookOut]:
    """Return a list of all books. Public access."""

    books = await repo.get_all()
    return [BookOut(**{
        "id": b.pk,
        "title": b.title,
        "author": b.author,
        "isbn": b.isbn,
        "copies": b.copies,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
    }) for b in books]


@router.post(
    "/books",
    response=BookOut,
    auth=HttpBearer(),
    operation_id="create_book",
    summary="Create book",
    description="Create a new book (Librarians only).",
)
async def create_book(request: Any, payload: BookIn) -> BookOut:
    """Create a new book. Requires `domain.add_book` permission."""

    # Enforce permission
    HasPerm(["domain.add_book"])(request)

    book = await repo.create(**payload.dict())
    return BookOut(**{
        "id": book.pk,
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "copies": book.copies,
        "created_at": book.created_at,
        "updated_at": book.updated_at,
    })


@router.put("/books/{book_id}", response=BookOut, summary="Update book")
async def update_book(request: Any, book_id: int, payload: BookIn) -> BookOut:
    """Update a book. Requires `domain.change_book` permission."""

    HasPerm(["domain.change_book"])(request)
    updated = await repo.update(book_id, **payload.dict())
    if updated is None:
        raise PermissionDenied("Book not found")
    return BookOut(**{
        "id": updated.pk,
        "title": updated.title,
        "author": updated.author,
        "isbn": updated.isbn,
        "copies": updated.copies,
        "created_at": updated.created_at,
        "updated_at": updated.updated_at,
    })


@router.delete("/books/{book_id}", summary="Delete book")
async def delete_book(request: Any, book_id: int) -> dict[str, bool]:
    """Delete a book. Requires `domain.delete_book` permission."""

    HasPerm(["domain.delete_book"])(request)
    deleted = await repo.delete(book_id)
    return {"deleted": deleted}


# Register router with global API
api.add_router("/", router)
