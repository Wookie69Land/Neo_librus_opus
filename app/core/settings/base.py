"""Base Django settings for Librarius.

This module uses `django-environ` to read environment variables and defines
the common settings shared by local and production configurations.
"""
from __future__ import annotations

import os
from pathlib import Path

from django.urls import reverse_lazy

from typing import Any, Dict, Final, List

import environ

BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent.parent.parent

# Load environment variables from a .env file if present.
env: environ.Env = environ.Env()
env.read_env(str(BASE_DIR / ".env"))

# Security
SECRET_KEY: Final[str] = env("SECRET_KEY", default="unsafe-secret-for-dev")
DEBUG: Final[bool] = env.bool("DEBUG", default=False)

ALLOWED_HOSTS: Final[List[str]] = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])  # type: ignore[arg-type]

# Application definition
INSTALLED_APPS: Final[List[str]] = [
    "unfold",
    "unfold.contrib.filters",  # Optional: Adds nice filter UI
    "unfold.contrib.forms",    # Optional: Adds nice form UI
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Project apps
    "app.domain.apps.DomainConfig",
]

MIDDLEWARE: Final[List[str]] = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF: Final[str] = "app.core.urls"

TEMPLATES: Final[List[Dict[str, Any]]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION: Final[str] = "app.core.wsgi.application"
ASGI_APPLICATION: Final[str] = "app.core.asgi.application"

DATABASES: Final[Dict[str, Any]] = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("MYSQL_DATABASE", default="librarius"),
        "USER": env("MYSQL_USER", default="root"),
        "PASSWORD": env("MYSQL_PASSWORD", default="password"),
        "HOST": env("MYSQL_HOST", default="db"),
        "PORT": env("MYSQL_PORT", default="3306"),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS: Final[List[Dict[str, str]]] = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE: Final[str] = "en-us"
TIME_ZONE: Final[str] = "UTC"
USE_I18N: Final[bool] = True
USE_TZ: Final[bool] = True

STATIC_URL: Final[str] = "/static/"

DEFAULT_AUTO_FIELD: Final[str] = "django.db.models.BigAutoField"


# Use custom user model from domain app
AUTH_USER_MODEL: Final[str] = "domain.CustomUser"


# UNFOLD Admin Panel Configuration
UNFOLD = {
    "SITE_TITLE": "Librarius Admin",
    "SITE_HEADER": "Librarius Administration",
    "SITE_URL": "/",
    # "SITE_ICON": lambda request: static("icon.svg"),  # optional
    "SIDEBAR": {
        "show_search": True,  # Search apps/models in sidebar
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Library Management",
                "separator": True,  # Adds a line before this section
                "items": [
                    {
                        "title": "Books Catalog",
                        "icon": "library_books",  # Material Icon name
                        "link": reverse_lazy("admin:domain_book_changelist"),
                    },
                    {
                        "title": "Loans & Returns",
                        "icon": "bookmark_added",
                        "link": reverse_lazy("admin:domain_reservation_changelist"),
                    },
                ],
            },
            {
                "title": "Users & Access",
                "separator": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "people",
                        "link": reverse_lazy("admin:domain_customuser_changelist"),
                    },
                    {
                        "title": "Groups",
                        "icon": "groups",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
        ],
    },
}
