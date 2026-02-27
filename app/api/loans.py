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
from app.domain.models import Reservation, Book
from app.domain.repository import AsyncRepository


class ReservationOut(Schema):
    id: int
    borrower_id: int
    book_id: int
    borrowed_at: datetime
    due_at: datetime
    returned_at: datetime | None = None


class ReservationIn(Schema):
    book_id: int
    due_at: datetime


router = Router(tags=["Reservations"])
repo = AsyncRepository(Reservation)
book_repo = AsyncRepository(Book)

