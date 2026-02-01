"""URL configuration for API endpoints.

This module mounts the django-ninja `api` application which exposes
the project's REST endpoints.
"""
from __future__ import annotations

from django.urls import include, path

from . import api as ninja_api

urlpatterns = [
    path("", ninja_api.api.urls),
]
