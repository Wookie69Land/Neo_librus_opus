"""Loans API router: create and view loans with validation and permissions.

This router provides endpoints for members to borrow books and for
librarians/admins to view loans.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from django.core.exceptions import PermissionDenied
from ninja import Router, Schema

from app.api.api import api
from app.domain.models import Loan, Book
from app.domain.repository import AsyncRepository


class LoanOut(Schema):
    id: int
    borrower_id: int
    book_id: int
    borrowed_at: datetime
    due_at: datetime
    returned_at: datetime | None = None


class LoanIn(Schema):
    book_id: int
    due_at: datetime


router = Router(tags=["Loans"])
repo = AsyncRepository(Loan)
book_repo = AsyncRepository(Book)


@router.get("/loans", response=List[LoanOut], summary="List loans", description="List loans (librarians/admins).")
async def list_loans(request: Any) -> List[LoanOut]:
    """List all loans. Requires view permissions for loans."""

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.has_perms(["domain.view_loan"]):
        raise PermissionDenied("Insufficient permissions")

    loans = await repo.get_all()
    return [LoanOut(**{
        "id": l.pk,
        "borrower_id": l.borrower_id,
        "book_id": l.book_id,
        "borrowed_at": l.borrowed_at,
        "due_at": l.due_at,
        "returned_at": l.returned_at,
    }) for l in loans]


@router.post("/loans", response=LoanOut, summary="Create loan", description="Create a loan (members).")
async def create_loan(request: Any, payload: LoanIn) -> LoanOut:
    """Create a loan for the authenticated user.

    Validates that the `due_at` is in the future and the book exists.
    """

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise PermissionDenied("Authentication required")

    # permission
    if not user.has_perms(["domain.add_loan"]):
        raise PermissionDenied("Insufficient permissions")

    # Validate due date
    now = datetime.now(timezone.utc)
    if payload.due_at <= now:
        raise ValueError("`due_at` must be a future datetime")

    # Validate book exists
    book = await book_repo.get_by_id(payload.book_id)
    if book is None:
        raise ValueError("Book not found")

    loan = await repo.create(borrower_id=user.pk, book_id=payload.book_id, due_at=payload.due_at)
    return LoanOut(**{
        "id": loan.pk,
        "borrower_id": loan.borrower_id,
        "book_id": loan.book_id,
        "borrowed_at": loan.borrowed_at,
        "due_at": loan.due_at,
        "returned_at": loan.returned_at,
    })


api.add_router("/", router)
