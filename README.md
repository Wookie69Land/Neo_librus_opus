# Librarius

Librarius is an async Django backend for a library management system with JWT-based API access, MySQL persistence, Redis-backed background jobs, curated seed data, and automated metadata enrichment.

## Overview

Main capabilities:

- account registration, activation, login, logout
- catalog management for books, authors, libraries, statuses, roles, and reservations
- authenticated search endpoints for simple and advanced book search
- scheduled background jobs for ISBN imports, Google Books enrichment, and random library assignment
- curated seed commands for Polish books and libraries

## Current Stack

- Python `>=3.12`
- Django `6.x`
- Django Ninja `1.x`
- MySQL `8.x`
- Redis `7.x`
- ARQ for background jobs
- Docker Compose for local and production-like environments

## Repository Layout

- `app/api/` — HTTP API routers, serializers, auth, and security
- `app/domain/` — Django models, domain services, management commands, and seed data
- `app/tasks/` — ARQ worker configuration and cyclic job implementations
- `app/core/settings/` — Django settings for local and production
- `DEPLOY.md` — deployment and operations guide
- `docs/API_REFERENCE.md` — detailed API documentation with permissions and examples

## Authentication Model

The API uses Bearer authentication backed by `SessionToken` rows.

Request pattern:

```http
Authorization: Bearer <signed_jwt_token>
```

Public endpoints:

- `POST /api/auth/register`
- `GET /api/auth/activate`
- `POST /api/auth/login`
- `POST /api/auth/logout`

All other endpoints currently require a valid bearer token.

Important current permission note:

- most CRUD endpoints are authenticated but not role-restricted
- `GET /api/users/{user_id}` is limited to the same user or a library worker
- `PUT /api/users/{user_id}` and `DELETE /api/users/{user_id}` are limited to the same user or a superuser

Detailed per-endpoint permission notes are in [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

## Local Development

### Option A — Docker Compose

Start local development services:

```bash
docker compose up --build -d
```

Services started by local compose:

- `web`
- `worker`
- `db`
- `redis`

Useful commands:

```bash
docker compose ps
docker compose logs -f web
docker compose logs -f worker
docker compose exec web python manage.py check
docker compose exec web python manage.py migrate
```

API docs:

```text
http://localhost:8000/api/docs
```

### Option B — Local Virtual Environment

If you already have a Python environment prepared:

```bash
python manage.py check
python manage.py migrate
python manage.py runserver
```

Note:

- `manage.py` defaults to `app.core.settings.local`
- local settings expect MySQL and Redis configured consistently with the compose file unless you override environment variables

## Management Commands

Domain commands currently available:

- `clear_books_data`
- `fetch_isbn_books`
- `run_cyclic_task`
- `seed_polish_books`
- `seed_polish_libraries`
- `show_cyclic_task_reports`

Examples in local Docker:

```bash
docker compose exec web python manage.py clear_books_data --force
docker compose exec web python manage.py fetch_isbn_books --limit 250 --batch-size 10 --no-verify-ssl
docker compose exec web python manage.py seed_polish_books
docker compose exec web python manage.py seed_polish_libraries
docker compose exec web python manage.py run_cyclic_task cyclic_book_manager
docker compose exec web python manage.py show_cyclic_task_reports --task cyclic_book_manager
```

Examples in local venv:

```bash
python manage.py clear_books_data --force
python manage.py fetch_isbn_books --limit 250 --batch-size 10 --no-verify-ssl
python manage.py seed_polish_books
python manage.py seed_polish_libraries
python manage.py run_cyclic_task cyclic_book_manager
python manage.py show_cyclic_task_reports --task cyclic_book_manager
```

Production Docker examples are documented in [DEPLOY.md](DEPLOY.md).

## Search Endpoints

The project exposes two authenticated search endpoints:

- `GET /api/search/books?q=<text>`
- `GET /api/search/books/advanced?...`

Simple search matches case-insensitively in:

- author name
- book title
- category
- ISBN
- publisher

Advanced search supports filtering by book fields and related author/library fields.

See [docs/API_REFERENCE.md](docs/API_REFERENCE.md) for the full parameter list.

## Background Jobs

ARQ worker jobs currently include:

- `cyclic_book_seeder`
- `cyclic_book_manager`
- `book_enricher`
- `assign_books_to_random_libraries`

Worker entrypoint:

```bash
arq app.tasks.worker.WorkerSettings
```

## Deployment And Operations

Use:

- [DEPLOY.md](DEPLOY.md) for deployment, environment variables, production commands, and smoke tests
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) for endpoint-by-endpoint API usage and current permission behavior