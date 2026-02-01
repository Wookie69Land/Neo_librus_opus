"""Production settings for Neo-Librus.

This module hardens a few default options and reads production secrets
from the environment.
"""
from __future__ import annotations

from typing import Final

from .base import *  # noqa: F401, F403

DEBUG = False

SENTRY_DSN: Final[str] = env("SENTRY_DSN", default="")

if SENTRY_DSN:
    try:  # pragma: no cover - optional runtime integration
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(dsn=SENTRY_DSN, integrations=[DjangoIntegration()])
    except Exception:
        pass

# Security-related settings
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Placeholder AWS/S3 static/media storage settings
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="")
