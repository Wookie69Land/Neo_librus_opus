"""ASGI entrypoint that defaults to local settings.

This module ensures `DJANGO_SETTINGS_MODULE` defaults to
`app.core.settings.local` when not provided, and exposes the standard
`application` object for ASGI servers.
"""
from __future__ import annotations

import os
from typing import Final

DEFAULT_SETTINGS: Final[str] = "app.core.settings.local"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", DEFAULT_SETTINGS)

from django.core.asgi import get_asgi_application  # noqa: E402

application = get_asgi_application()
