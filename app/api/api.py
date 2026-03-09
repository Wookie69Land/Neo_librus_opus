"""Django-Ninja API application and global exception handlers.

Defines the :data:`api` object used to register routers and exception
handlers across the project.
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from ninja import NinjaAPI

from . import auth, authors, books, libraries, reservations, roles, statuses

api = NinjaAPI(
    title="Librarius API",
    version="0.1.0",
    description=(
        "Async Django + Ninja API for the Librarius library backend.\n\n"
        "Endpoints are documented with Pydantic schemas and use async ORM operations."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)

api.add_router("/books", books.router)
api.add_router("/authors", authors.router)
api.add_router("/libraries", libraries.router)
api.add_router("/reservations", reservations.router)
api.add_router("/roles", roles.router)
api.add_router("/statuses", statuses.router)
api.add_router("/auth", auth.router)


@api.exception_handler(PermissionDenied)
def permission_denied(
    request: Any, exc: PermissionDenied
) -> JsonResponse:  # pragma: no cover - behaviour wrapper
    """Return a JSON 403 response when Django raises PermissionDenied.

    This keeps API error shapes consistent for clients.
    """

    return JsonResponse({"detail": str(exc)}, status=403)

