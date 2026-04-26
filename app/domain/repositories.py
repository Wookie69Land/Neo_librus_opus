from __future__ import annotations

import logging

from django.db.models import Count, Q, Prefetch

from app.domain.languages import normalize_language_to_iso3
from app.domain.models import (
    Author,
    Book,
    BookAuthor,
    Library,
    LibraryAdmin,
    LibraryBook,
    LibraryUser,
    Reservation,
    Role,
    Status,
)
from app.domain.repository import AsyncRepository


class BookRepository(AsyncRepository[Book]):
    pass


class AuthorRepository(AsyncRepository[Author]):
    pass


class LibraryRepository(AsyncRepository[Library]):
    pass


class ReservationRepository(AsyncRepository[Reservation]):
    pass


class StatusRepository(AsyncRepository[Status]):
    pass


class RoleRepository(AsyncRepository[Role]):
    pass


class LibraryUserRepository(AsyncRepository[LibraryUser]):
    async def get_by_username_or_email(self, login: str):
        try:
            if "@" in login:
                return await self.model.objects.aget(email=login.strip().lower())
            else:
                return await self.model.objects.aget(username=login.strip())
        except self.model.DoesNotExist:
            return None


class LibraryBookRepository(AsyncRepository[LibraryBook]):
    pass


class LibraryAdminRepository(AsyncRepository[LibraryAdmin]):
    async def is_admin(self, user_id: int) -> bool:
        return await self.model.objects.filter(user_id=user_id).aexists()

    async def get_admin_library_ids(self, user_id: int) -> list[int]:
        return [
            admin.library.id
            async for admin in self.model.objects.filter(user_id=user_id)
        ]


class BookAuthorRepository(AsyncRepository[BookAuthor]):
    pass


class RecommendationRepository:
    """Async repository methods used exclusively by the AI recommendation pipeline.

    All methods return plain ``dict`` objects so they can be serialised to JSON
    and passed across the ARQ task boundary without Django ORM objects.
    """

    _logger = logging.getLogger(__name__)

    async def fetch_candidates(
        self,
        *,
        keywords: list[str],
        language: str | None = None,
        include_unavailable: bool = True,
        period_from: int | None = None,
        period_to: int | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Retrieve candidate books matching the given keywords.

        Searches across title, category, description, and author names using
        case-insensitive substring matching. Results are ordered by the number
        of library copies (popularity proxy) descending.

        Args:
            keywords: Search terms extracted by the query-understanding node.
            language: Optional ISO 639-1 code to narrow results.
            include_unavailable: When False, only books with at least one
                available library copy are returned.
            period_from: Optional minimum publication year (inclusive).
            period_to: Optional maximum publication year (inclusive).
            limit: Maximum number of books to return (default 50).

        Returns:
            List of dicts, each containing book metadata plus availability info.
        """
        self._logger.info(
            "fetch_candidates called: keywords=%s language=%r include_unavailable=%s "
            "period=%s-%s limit=%d",
            keywords, language, include_unavailable, period_from, period_to, limit,
        )

        keyword_filter = Q()
        for kw in keywords:
            keyword_filter |= (
                Q(title__icontains=kw)
                | Q(category__icontains=kw)
                | Q(description__icontains=kw)
                | Q(authors__name__icontains=kw)
            )

        qs = (
            Book.objects.filter(keyword_filter)
            .prefetch_related(
                Prefetch(
                    "librarybook_set",
                    queryset=LibraryBook.objects.select_related("library"),
                    to_attr="library_copies",
                ),
                "authors",
            )
            .annotate(copy_count=Count("librarybook", distinct=True))
            .order_by("-copy_count", "title")
            .distinct()
        )

        if language:
            qs = qs.filter(language__iexact=normalize_language_to_iso3(language))
        if period_from is not None:
            qs = qs.filter(published_year__gte=period_from)
        if period_to is not None:
            qs = qs.filter(published_year__lte=period_to)
        if not include_unavailable:
            qs = qs.filter(librarybook__is_available=True)

        results: list[dict] = []
        async for book in qs[:limit]:
            library_copies: list[LibraryBook] = getattr(book, "library_copies", [])
            available_copies = sum(1 for lb in library_copies if lb.is_available)
            results.append(
                {
                    "book_id": book.id,
                    "title": book.title,
                    "isbn": book.isbn,
                    "authors": [a.name for a in book.authors.all()],
                    "language": book.language,
                    "category": book.category,
                    "published_year": book.published_year,
                    "description": book.description,
                    "cover_url": book.cover_url,
                    "available_copies": available_copies,
                    "total_copies": len(library_copies),
                    "availability": [
                        {
                            "library_id": lb.library_id,
                            "library_name": lb.library.name,
                            "is_available": lb.is_available,
                        }
                        for lb in library_copies
                    ],
                }
            )
        self._logger.info("fetch_candidates result: %d books returned", len(results))
        return results
