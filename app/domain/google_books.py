"""Google Books API client used by background enrichment jobs."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from unidecode import unidecode

logger = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _slugify(value: str) -> str:
    return " ".join(
        "".join(char.lower() if char.isalnum() else " " for char in unidecode(value)).split()
    )


@dataclass(slots=True)
class GoogleBooksVolume:
    """Normalized subset of Google Books volume metadata."""

    google_id: str
    title: str | None
    authors: list[str]
    categories: list[str]
    cover_url: str | None
    raw: dict[str, Any]


class GoogleBooksTemporaryError(RuntimeError):
    """Raised when Google Books is temporarily unavailable or the network is unstable."""


class GoogleBooksClient:
    """Minimal async client for the Google Books Volumes API."""

    base_url = "https://www.googleapis.com/books/v1"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 15.0,
        max_results: int = 5,
        retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.max_results = max_results
        self.retries = max(retries, 1)
        self.retry_backoff_seconds = max(retry_backoff_seconds, 0.0)

    async def _request_volumes(self, *, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(1, self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(f"{self.base_url}/volumes", params=params)

                if response.status_code in RETRYABLE_STATUS_CODES:
                    error = GoogleBooksTemporaryError(
                        f"Google Books temporary failure {response.status_code} for query {params.get('q')!r}"
                    )
                    last_error = error
                    if attempt == self.retries:
                        raise error

                    logger.warning(
                        "Retryable Google Books response",
                        extra={
                            "status_code": response.status_code,
                            "attempt": attempt,
                            "query": params.get("q"),
                        },
                    )
                    await asyncio.sleep(self.retry_backoff_seconds * attempt)
                    continue

                response.raise_for_status()
                return response.json()
            except httpx.RequestError as exc:
                last_error = exc
                if attempt == self.retries:
                    raise GoogleBooksTemporaryError(
                        f"Google Books request failed after {attempt} attempts for query {params.get('q')!r}: {exc}"
                    ) from exc

                logger.warning(
                    "Google Books request error, retrying",
                    extra={
                        "attempt": attempt,
                        "query": params.get("q"),
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(self.retry_backoff_seconds * attempt)

        if isinstance(last_error, GoogleBooksTemporaryError):
            raise last_error
        raise GoogleBooksTemporaryError(
            f"Google Books request failed for query {params.get('q')!r}"
        )

    async def search(self, *, query: str, projection: str = "lite", max_results: int | None = None) -> list[GoogleBooksVolume]:
        """Search the Google Books catalog with a generic volumes query."""

        params: dict[str, Any] = {
            "q": query,
            "projection": projection,
            "printType": "books",
            "maxResults": max_results or self.max_results,
        }
        if self.api_key:
            params["key"] = self.api_key

        payload = await self._request_volumes(params=params)

        items = payload.get("items", [])
        return [self._normalise_volume(item) for item in items]

    async def search_by_isbn(self, isbn: str) -> list[GoogleBooksVolume]:
        """Search volumes by ISBN."""

        return await self.search(query=f"isbn:{isbn}", max_results=3)

    async def search_by_title_author(self, *, title: str, authors: list[str]) -> list[GoogleBooksVolume]:
        """Search volumes by title and the primary author."""

        query = f'intitle:"{title}"'
        if authors:
            query += f' inauthor:"{authors[0]}"'
        return await self.search(query=query)

    async def best_match(self, *, isbn: str | None, title: str, authors: list[str]) -> GoogleBooksVolume | None:
        """Return the best Google Books match using ISBN first and title/author fallback."""

        candidates: list[GoogleBooksVolume] = []
        if isbn:
            candidates.extend(await self.search_by_isbn(isbn))
        if not candidates:
            candidates.extend(await self.search_by_title_author(title=title, authors=authors))
        if not candidates:
            return None

        title_slug = _slugify(title)
        author_slugs = {_slugify(author) for author in authors}

        def score(volume: GoogleBooksVolume) -> tuple[int, int]:
            volume_title = _slugify(volume.title or "")
            volume_authors = {_slugify(author) for author in volume.authors}
            exact_title = int(volume_title == title_slug)
            title_overlap = int(title_slug in volume_title or volume_title in title_slug)
            author_overlap = len(author_slugs & volume_authors)
            return (exact_title * 100 + title_overlap * 25 + author_overlap * 20, len(volume.categories))

        candidates.sort(key=score, reverse=True)
        best = candidates[0]
        if score(best)[0] <= 0:
            return None
        return best

    def _normalise_volume(self, item: dict[str, Any]) -> GoogleBooksVolume:
        volume_info = item.get("volumeInfo", {})
        image_links = volume_info.get("imageLinks", {})
        cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        if cover_url:
            cover_url = cover_url.replace("http://", "https://")
        return GoogleBooksVolume(
            google_id=item.get("id", ""),
            title=volume_info.get("title"),
            authors=list(volume_info.get("authors", [])),
            categories=list(volume_info.get("categories", [])),
            cover_url=cover_url,
            raw=item,
        )
