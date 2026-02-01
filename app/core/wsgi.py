"""WSGI entrypoint for Neo-Librus.

Exposes the WSGI application for compatibility with traditional servers.
"""
from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.core.settings.local")

application = get_wsgi_application()
