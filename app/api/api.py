"""Django-Ninja API application and global exception handlers.

Defines the :data:`api` object used to register routers and exception
handlers across the project.
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from ninja import NinjaAPI

api = NinjaAPI(
    title="Neo-Librus API",
    version="0.1.0",
    description=(
        "Async Django + Ninja API for the Neo-Librus library backend.\n\n"
        "Endpoints are documented with Pydantic schemas and use async ORM operations."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Import router modules so they register on import (side-effect registers routers)
from . import books  # noqa: F401
from . import loans  # noqa: F401


@api.exception_handler(PermissionDenied)
def permission_denied(request: Any, exc: PermissionDenied) -> JsonResponse:  # pragma: no cover - behaviour wrapper
    """Return a JSON 403 response when Django raises PermissionDenied.

    This keeps API error shapes consistent for clients.
    """

    return JsonResponse({"detail": str(exc)}, status=403)
