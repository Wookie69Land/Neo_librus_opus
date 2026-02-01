"""AppConfig for the domain app.

Defines the application configuration for `app.domain` which contains
models and business logic for Neo-Librus.
"""
from __future__ import annotations

from django.apps import AppConfig


class DomainConfig(AppConfig):
    """Application configuration for the domain package.

    The `name` should match the import path for the package.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "app.domain"
    verbose_name = "Neo-Librus Domain"
