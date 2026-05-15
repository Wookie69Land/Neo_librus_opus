# Librarius API Reference

This document describes the current HTTP API exposed under `/api`.

Base URL examples:

- local: `http://localhost:8000/api`
- production: `https://librarius-api.nanys.pl/api`

## Authentication

Global API authentication is configured in `app/api/api.py` with Bearer auth from `app/api/security.py`.

Authenticated request header:

```http
Authorization: Bearer <signed_jwt_token>
```

How it works currently:

- the bearer token must match a `SessionToken.key` row
- if the token is missing or invalid, authenticated endpoints return unauthorized responses through Django Ninja auth handling
- logout does not use the Authorization header; it accepts the token in the JSON body

## Permission Summary

Current effective permissions:

- `POST /auth/register` — public
- `GET /auth/activate` — public
- `POST /auth/login` — public
- `POST /auth/logout` — public, but requires a valid token string in the request body to invalidate the active session
- `POST /auth/password-reset/request` — public
- `POST /auth/password-reset/confirm` — public
- all `/authors`, `/books`, `/libraries`, `/reservations`, `/roles`, `/statuses`, `/search` endpoints — authenticated user required
- `GET /users/{user_id}` — authenticated user required; allowed for the same user or any library worker with `role_id != 0`
- `PUT /users/{user_id}` — authenticated user required; allowed for the same user or a superuser
- `DELETE /users/{user_id}` — authenticated user required; allowed for the same user or a superuser

Important note:

- there is currently no additional role-based access control on most CRUD endpoints, so any authenticated user can create, update, and delete authors, books, libraries, roles, statuses, and reservations

## Auth Endpoints

### POST `/auth/register`

Permission:

- public

Request body:

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!",
  "first_name": "Jan",
  "last_name": "Kowalski",
  "region": 7
}
```

Validation rules:

- email must be syntactically valid
- first and last name must contain letters and may contain spaces, apostrophes, and hyphens
- password must be at least 12 characters and include uppercase, digit, and special character

How to call this endpoint:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "StrongPass123!",
    "first_name": "Jan",
    "last_name": "Kowalski",
    "region": 7
  }'
```

Production example:

```bash
curl -X POST https://librarius-api.nanys.pl/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "StrongPass123!",
    "first_name": "Jan",
    "last_name": "Kowalski",
    "region": 7
  }'
```

Important request details:

- use method `POST`
- send header `Content-Type: application/json`
- do not send Bearer token; this endpoint is public
- `region` is optional, the rest of the fields are required

Responses:

- `201` — created, inactive user returned
- `409` — email or username conflict
- `422` — input validation failed
- `500` — activation e-mail failed or unexpected registration error

### GET `/auth/activate`

Permission:

- public

Query parameters:

- `uid`
- `token`

Responses:

- `302` — successful activation, redirects to the frontend success page
- `400` — invalid activation link

Default redirect target:

```text
https://librarius.nanys.pl/register-success
```

### POST `/auth/login`

Permission:

- public

Request body:

```json
{
  "login": "user@example.com",
  "password": "StrongPass123!"
}
```

Notes:

- `login` accepts either username or email
- successful login updates `last_login`
- successful login creates or replaces the current `SessionToken`

Responses:

- `200` — returns signed JWT token string
- `401` — invalid credentials or inactive account

### POST `/auth/logout`

Permission:

- public endpoint

Request body:

```json
{
  "token": "<signed_jwt_token>"
}
```

Responses:

- `200` — logout successful or no active session found
- `400` — invalid token format
- `409` — token belongs to a different active session than the current one stored for the user

### POST `/auth/password-reset/request`

Permission:

- public

#### Purpose

Initiates a password reset flow for a user identified by email address. If an active account with the given email exists, a one-time reset link is sent to that address. The link embeds a signed token valid for a configurable period (default 1 hour).

#### Request body

```json
{
  "email": "user@example.com"
}
```

#### Responses

- `200` — always returned after lookup (see body for result)
- `500` — SMTP failure; the email could not be sent

#### 200 body — user found

```json
{
  "user_id": 42
}
```

#### 200 body — no active account with that email

```json
{
  "user_id": null
}
```

#### Email content

The user receives a plain-text email with a link in the following form:

```
https://librarius.nanys.pl/reset-password?uid=<base64-user-id>&token=<signed-token>
```

The frontend must present this as a clickable link that opens the password-reset form.

#### Notes

- only accounts with `is_active = true` receive the email; inactive accounts silently return `user_id: null`
- token validity window is controlled by the `PASSWORD_RESET_TIMEOUT` environment variable (seconds, default `3600`)
- the token automatically becomes invalid once the password changes, so replay attacks are not possible
- the response intentionally distinguishes registered from unknown emails; consider rate-limiting this endpoint at the infrastructure level to limit enumeration

#### curl example

```bash
curl -X POST http://localhost:8000/api/auth/password-reset/request \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

---

### POST `/auth/password-reset/confirm`

Permission:

- public

#### Purpose

Validates the one-time token from the reset link and sets the new password. On success the user's active session is revoked and they must log in again.

#### Request body

```json
{
  "uid": "<base64-user-id from reset URL>",
  "token": "<signed-token from reset URL>",
  "new_password": "NewStrongPass1!"
}
```

`uid` and `token` are the raw query parameter values from the reset URL received in the email.

#### Password requirements (same as registration)

- minimum 12 characters
- at least one uppercase letter
- at least one digit
- at least one special character
- must not be too similar to user attributes or be a common password

#### Responses

- `200` — password changed; existing session invalidated
- `400` — invalid or expired token / unknown user
- `422` — new password failed validation rules

#### 200 body

```json
{
  "detail": "Password reset successful. Please log in with your new password."
}
```

#### 400 body

```json
{
  "detail": "Invalid or expired password reset link"
}
```

Both invalid uid and expired/wrong token return the same 400 message to avoid leaking which part failed.

#### 422 body

```json
{
  "detail": ["This password is too common.", "This password must contain at least 1 uppercase letter."]
}
```

#### curl example

```bash
curl -X POST http://localhost:8000/api/auth/password-reset/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "uid": "NDI",
    "token": "bw3grl-...",
    "new_password": "NewStrongPass1!"
  }'
```

---

#### Full password reset flow

```
User                           Frontend                        API
 │                                │                             │
 │── clicks "Forgot password" ───►│                             │
 │                                │── POST /auth/password-reset/request (email) ──►│
 │                                │◄── 200 { user_id: 42 | null } ─────────────────│
 │                                │                             │
 │◄── show "check your email" ────│    (if user_id != null)     │
 │                                │          email sent ──────► user inbox
 │                                │                             │
 │── clicks link in email ────────►│                             │
 │  (?uid=NDI&token=bw3grl-...)   │                             │
 │                                │  parse uid + token from URL │
 │                                │── POST /auth/password-reset/confirm ──────────►│
 │                                │   { uid, token, new_password }                  │
 │                                │◄── 200 { detail: "Password reset successful" } ─│
 │                                │                             │
 │◄── redirect to /login ─────────│  session invalidated         │
```

## Search Endpoints

### GET `/search/books`

Permission:

- public

Query parameters:

- `q` — required free-text query
- `page` — optional, defaults to `1`
- `page_size` — optional, defaults to `20`, maximum `50`

Current matching fields, case-insensitive:

- `authors.name`
- `books.title`
- `books.category`
- `books.isbn`
- `books.publisher`

Responses:

- `200` — paginated list of matching books
- `422` — empty query string

Notes:

- this route is currently public in code
- if you send a valid bearer token, each result's `libraries` array is ordered so the caller's region appears first

### GET `/search/books/advanced`

Permission:

- authenticated user required

Supported query parameters:

- `page` — optional, defaults to `1`
- `page_size` — optional, defaults to `20`, maximum `50`
- `id`
- `title`
- `isbn`
- `integration_source`
- `data_source`
- `google_id`
- `publisher`
- `published_year`
- `published_year_min`
- `published_year_max`
- `description`
- `page_count`
- `page_count_min`
- `page_count_max`
- `print_type`
- `category`
- `cover_url`
- `language`
- `languages` — repeated query parameter or comma-separated list
- `author_id`
- `author_ids` — repeated query parameter or comma-separated list
- `author_name`
- `author_names` — repeated query parameter or comma-separated list
- `library_id`
- `library_name`
- `library_city`
- `library_region`
- `is_available`

Example:

```http
GET /api/search/books/advanced?author_name=sienkiewicz&library_city=warszawa&is_available=true
Authorization: Bearer <signed_jwt_token>
```

Multi-value examples:

```http
GET /api/search/books/advanced?languages=eng&languages=pol&author_names=Adam%20Mickiewicz&author_names=Witold%20Gombrowicz
Authorization: Bearer <signed_jwt_token>
```

```http
GET /api/search/books/advanced?author_ids=12,18&languages=eng,pol
Authorization: Bearer <signed_jwt_token>
```

How to call this endpoint with `curl`:

```bash
curl -G http://localhost:8000/api/search/books/advanced \
  -H "Authorization: Bearer <signed_jwt_token>" \
  --data-urlencode "title=pan" \
  --data-urlencode "languages=eng" \
  --data-urlencode "languages=pol" \
  --data-urlencode "author_names=Adam Mickiewicz" \
  --data-urlencode "author_names=Witold Gombrowicz" \
  --data-urlencode "library_city=Warszawa" \
  --data-urlencode "is_available=true"
```

Equivalent production example:

```bash
curl -G https://librarius-api.nanys.pl/api/search/books/advanced \
  -H "Authorization: Bearer <signed_jwt_token>" \
  --data-urlencode "author_ids=12,18" \
  --data-urlencode "languages=eng,pol" \
  --data-urlencode "library_region=7"
```

Important request details:

- use method `GET`
- send header `Authorization: Bearer <signed_jwt_token>`
- for repeated filters you can repeat the same query parameter many times
- for multi-value filters you can also send comma-separated values in one parameter
- spaces and Polish characters should be sent through `--data-urlencode` when using `curl`

Responses:

- `200` — paginated list of matching books

Notes:

- each result includes `libraries` with live availability metadata
- if the authenticated user has a region, matching-region libraries are sorted first

Response shape for both search endpoints:

```json
{
  "items": [
    {
      "id": 1,
      "title": "Quo Vadis",
      "isbn": "9788324012345",
      "integration_source": 20,
      "data_source": "curated-polish-top100",
      "google_id": null,
      "publisher": "PIW",
      "published_year": 1896,
      "description": "...",
      "page_count": 550,
      "print_type": "PAPERBACK",
      "category": "Powieść historyczna",
      "cover_url": "https://...",
      "language": "pol",
      "last_updated": "2026-03-26T10:00:00Z",
      "authors": [
        {
          "id": 5,
          "name": "Henryk Sienkiewicz"
        }
      ],
      "libraries": [
        {
          "id": 1,
          "name": "Biblioteka Narodowa",
          "city": "Warszawa",
          "region": 7,
          "is_available": true,
          "availability_checked_at": "2026-04-13T18:30:00Z",
          "availability_source": "mock-library-api"
        }
      ]
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "total_pages": 1
}
```

## Books Endpoints

Permission differs by route:

- `GET /books` — public
- `GET /books/{book_id}` — public
- `GET /books/{book_id}/availability` — public
- `GET /books/languages` — authenticated user required
- `POST /books` — authenticated user required and library admin or superuser required
- `PUT /books/{book_id}` — authenticated user required and library admin or superuser required
- `DELETE /books/{book_id}` — authenticated user required and library admin or superuser required

Routes:

- `GET /books` — list all books
- `GET /books/languages` — list normalized language codes present in stored books
- `POST /books` — create a book
- `GET /books/{book_id}` — fetch one book with per-library availability
- `GET /books/{book_id}/availability` — fetch only the live availability block for one book
- `PUT /books/{book_id}` — update a book
- `DELETE /books/{book_id}` — delete a book

Create/update body:

```json
{
  "title": "Book title",
  "isbn": "9788324012345",
  "publisher": "Publisher",
  "published_year": 2024,
  "page_count": 250,
  "cover_url": "https://example.com/cover.jpg",
  "language": "pol",
  "author_ids": [1, 2]
}
```

Current notes:

- ISBN is normalized before save
- author links are recreated on update
- `GET /books/{book_id}` now returns the base book payload plus a `libraries` array
- availability checks currently use the mock source string `mock-library-api`
- when a valid bearer token is provided on public availability endpoints, libraries from the caller's region are listed first

Example availability response:

```json
{
  "book_id": 1,
  "title": "Quo Vadis",
  "user_region": 7,
  "checked_via": "mock-library-api",
  "libraries": [
    {
      "id": 3,
      "name": "Biblioteka Warszawa",
      "city": "Warszawa",
      "region": 7,
      "is_available": true,
      "availability_checked_at": "2026-04-13T18:30:00Z",
      "availability_source": "mock-library-api"
    }
  ]
}
```

## Authors Endpoints

Permission:

- authenticated user required
- no extra role restriction currently enforced

Routes:

- `GET /authors`
- `POST /authors`
- `GET /authors/{author_id}`
- `PUT /authors/{author_id}`
- `DELETE /authors/{author_id}`

Body for create/update:

```json
{
  "name": "Henryk Sienkiewicz"
}
```

## Libraries Endpoints

Permission:

- authenticated user required
- no extra role restriction currently enforced

Routes:

- `GET /libraries`
- `POST /libraries`
- `GET /libraries/{library_id}`
- `PUT /libraries/{library_id}`
- `DELETE /libraries/{library_id}`

Create/update body:

```json
{
  "name": "Biblioteka Narodowa",
  "address": "al. Niepodległości 213",
  "city": "Warszawa",
  "phone": "+48 22 608 29 99",
  "email": "kontakt@bn.org.pl",
  "region": 7
}
```

## Reservations Endpoints

### Reservation status flow

```
                    ┌─(admin PUT → rejected)──► rejected
                    │
pending ────────────┼─(user DELETE → cancelled)─► cancelled
                    │
                    ├─(system, 48 h no action)──► expired
                    │
                    └─(admin PUT → accepted)──► accepted ─┬─(system, 3 days)──► closed
                                                           │
                                                           └─(user DELETE)──────► cancelled
```

Three actors:

- **User** — creates reservations and can cancel their own reservation while it is `pending` or `accepted`.
- **Library admin** — can accept or reject a `pending` reservation that belongs to their library.
- **System** (`reservation_manager` cron task, runs every minute) — automatically expires `pending` reservations that have not been actioned in 48 hours, and closes `accepted` reservations after 3 days.

### Permissions

- `GET /reservations` — authenticated user required; regular users see only their own; library admins see only their library's; superusers see all
- `POST /reservations` — any authenticated user
- `GET /reservations/{id}` — owner or library admin of that reservation's library
- `PUT /reservations/{id}` — library admin only; accepts or rejects a pending reservation
- `DELETE /reservations/{id}` — owner only; cancels the reservation (allowed from `pending` or `accepted`)

### Routes

- `GET /reservations`
- `POST /reservations`
- `GET /reservations/{reservation_id}`
- `PUT /reservations/{reservation_id}`
- `DELETE /reservations/{reservation_id}`

### POST `/reservations` — Create a reservation

Request body:

```json
{
  "library_id": 1,
  "book_id": 10
}
```

Validation:

- book must exist
- library must exist
- book must be linked to that library via `LibraryBook`

Responses:

- `200` — created reservation with `status.name = "pending"`
- `404` — book or library not found
- `422` — book not available in that library

### PUT `/reservations/{reservation_id}` — Admin accept or reject

Request body:

```json
{
  "status_id": 3
}
```

Only the following transition is allowed:

- `pending` → `accepted`
- `pending` → `rejected`

Responses:

- `200` — updated reservation
- `403` — caller is not an admin of the reservation's library
- `404` — reservation not found or status not found
- `422` — transition not allowed from current status

### DELETE `/reservations/{reservation_id}` — User cancel

No body required. Cancels the reservation by setting status to `cancelled`.

Allowed from:

- `pending`
- `accepted`

Responses:

- `200` — `{"success": true}`
- `403` — caller is not the reservation owner
- `404` — reservation not found
- `422` — current status does not allow cancellation

### Automatic status transitions (system)

The `reservation_manager` background task runs every minute and performs:

| Condition | Transition |
|---|---|
| `status = pending` AND `updated_at` older than 48 hours | `pending` → `expired` |
| `status = accepted` AND `updated_at` older than 3 days | `accepted` → `closed` |

The `updated_at` field on `Reservation` is updated by `auto_now` on every save. For the system task it acts as the last-status-change timestamp, since every admin action calls `asave(update_fields=[..., "updated_at"])`.

### Response shape

```json
{
  "id": 42,
  "status": {"id": 1, "name": "pending"},
  "start_time": "2026-04-29T10:00:00Z",
  "end_time": null,
  "reader": {"id": 5, "username": "jkowalski", "email": "jkowalski@example.com", "first_name": "Jan", "last_name": "Kowalski", "region": 7, "is_active": true, "date_joined": "2026-01-01T00:00:00Z", "last_login": null},
  "librarian": null,
  "library": {"id": 1, "name": "Biblioteka Testowa", "city": "Warszawa", "region": 7},
  "book": {"id": 10, "title": "Pan Tadeusz", "isbn": "9788324012345", ...}
}
```

## Roles Endpoints

Permission:

- authenticated user required
- no extra role restriction currently enforced

Routes:

- `GET /roles`
- `POST /roles`
- `GET /roles/{role_id}`
- `PUT /roles/{role_id}`
- `DELETE /roles/{role_id}`

## Statuses Endpoints

Permission:

- authenticated user required
- no extra role restriction currently enforced

Routes:

- `GET /statuses`
- `POST /statuses`
- `GET /statuses/{status_id}`
- `PUT /statuses/{status_id}`
- `DELETE /statuses/{status_id}`

## Users Endpoints

### GET `/users/{user_id}`

Permission:

- authenticated user required
- same user or library worker only

Response:

- `200` — detailed user data with active reservations and library roles
- `403` — permission denied
- `404` — user not found

### PUT `/users/{user_id}`

Permission:

- authenticated user required
- same user or superuser only

Allowed fields:

- `email`
- `first_name`
- `last_name`
- `region`
- `password`

Responses:

- `200` — updated user plus refreshed token for self-service updates
- `403` — permission denied
- `404` — user not found
- `422` — validation error

Response shape:

```json
{
  "user": {
    "id": 7,
    "username": "jkowalski",
    "email": "updated@example.com",
    "first_name": "Jan",
    "last_name": "Kowalski",
    "region": 11,
    "is_active": true,
    "date_joined": "2026-04-01T09:00:00Z",
    "last_login": "2026-04-13T18:45:00Z"
  },
  "token": "<refreshed_jwt_token>"
}
```

Notes:

- the refreshed `token` is returned when a user updates their own profile
- frontend clients should replace the current bearer token with the returned token after a successful self-update

### DELETE `/users/{user_id}`

Permission:

- authenticated user required
- same user or superuser only

Responses:

- `200` — deleted
- `403` — permission denied
- `404` — user not found

## Common Error Shapes

Examples:

```json
{"detail": "Invalid credentials"}
```

```json
{"detail": ["This password must contain at least one uppercase letter."]}
```

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "email"],
      "msg": "Value error, Enter a valid email address.",
      "input": "usertestowy.pl"
    }
  ]
}
```
