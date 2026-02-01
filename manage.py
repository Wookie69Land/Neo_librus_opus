"""Django management entrypoint that defaults to local settings.

This file sets DJANGO_SETTINGS_MODULE to `app.core.settings.local`
when not provided, to simplify local development.
"""
from __future__ import annotations

import os
import sys
from typing import Final

DEFAULT_SETTINGS: Final[str] = "app.core.settings.local"


def main() -> None:
    """Run administrative tasks for the Django project.

    If the environment variable `DJANGO_SETTINGS_MODULE` is not set, this
    defaults it to :data:`DEFAULT_SETTINGS`.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", DEFAULT_SETTINGS)

    try:
        from django.core.management import execute_from_command_line
    except Exception:  # pragma: no cover - bootstrapping
        raise
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
