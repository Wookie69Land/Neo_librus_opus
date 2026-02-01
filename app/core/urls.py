"""Root URL configuration for Neo-Librus.

This module exposes a minimal URLconf used during bootstrapping. More
API routes will be registered under the `api` package.
"""
from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("app.api.urls")),
]
