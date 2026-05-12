"""Minimal SQLite settings for running management commands locally without MySQL/Docker.

Used only for smoke-testing management commands during development.
Not for running the test suite (use `test.py` for that).

Usage:
    python manage.py migrate --settings=app.core.settings.smoketest
    python manage.py seed_factory_data --settings=app.core.settings.smoketest
"""
from __future__ import annotations

from .base import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "smoketest.sqlite3",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

DEBUG = True
