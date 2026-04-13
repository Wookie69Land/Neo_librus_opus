from __future__ import annotations

import asyncio
import random
from datetime import timedelta

from django.db.models import Case, IntegerField, Value, When
from django.http import HttpRequest
from django.utils import timezone

from app.api.serializers import BookLibraryAvailabilitySchema
from app.domain.models import LibraryBook, LibraryUser, SessionToken

MOCK_AVAILABILITY_SOURCE = "mock-library-api"
FRESH_AVAILABILITY_WINDOW = timedelta(minutes=5)


async def get_optional_request_user(request: HttpRequest) -> LibraryUser | None:
    session = getattr(request, "auth", None)
    user = getattr(session, "user", None)
    if user is not None:
        return user

    authorization_header = request.headers.get("Authorization", "")
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None

    session = await SessionToken.objects.select_related("user").filter(key=token.strip()).afirst()
    if session is None:
        return None

    return session.user


async def get_request_user_region(request: HttpRequest) -> int | None:
    user = await get_optional_request_user(request)
    if user is None:
        return None
    return user.region


async def mock_library_api_availability_check(
    library_book: LibraryBook,
) -> BookLibraryAvailabilitySchema:
    await asyncio.sleep(0)
    checked_at = timezone.now()
    if library_book.book.last_updated >= checked_at - FRESH_AVAILABILITY_WINDOW:
        is_available = library_book.is_available
    else:
        is_available = random.random() < 0.75

    if library_book.is_available != is_available:
        library_book.is_available = is_available
        await library_book.asave(update_fields=["is_available"])

    return BookLibraryAvailabilitySchema(
        id=library_book.library_id,
        name=library_book.library.name,
        city=library_book.library.city,
        region=library_book.library.region,
        is_available=is_available,
        availability_checked_at=checked_at,
        availability_source=MOCK_AVAILABILITY_SOURCE,
    )


async def get_book_library_availability(
    book_id: int,
    *,
    user_region: int | None,
) -> list[BookLibraryAvailabilitySchema]:
    library_books = LibraryBook.objects.select_related("library", "book").filter(book_id=book_id)
    if user_region is not None:
        library_books = library_books.annotate(
            user_region_priority=Case(
                When(library__region=user_region, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("user_region_priority", "library__name", "library_id")
    else:
        library_books = library_books.order_by("library__name", "library_id")

    libraries: list[BookLibraryAvailabilitySchema] = []
    async for library_book in library_books:
        libraries.append(await mock_library_api_availability_check(library_book))

    return libraries