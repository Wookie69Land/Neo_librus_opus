"""Local (development) settings for Neo-Librus.

Sets `DEBUG = True` and uses the console email backend.
"""
from __future__ import annotations

from .base import *  # noqa: F401, F403

DEBUG = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
