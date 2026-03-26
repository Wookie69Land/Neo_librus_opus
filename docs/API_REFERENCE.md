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

## Search Endpoints

### GET `/search/books`

Permission:

- authenticated user required

Query parameters:

- `q` — required free-text query

Current matching fields, case-insensitive:

- `authors.name`
- `books.title`
- `books.category`
- `books.isbn`
- `books.publisher`

Responses:

- `200` — list of matching books
- `422` — empty query string

### GET `/search/books/advanced`

Permission:

- authenticated user required

Supported query parameters:

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
- `author_id`
- `author_name`
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

Response shape for both search endpoints:

```json
[
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
        "is_available": true
      }
    ]
  }
]
```

## Books Endpoints

Permission for all book endpoints:

- authenticated user required
- no extra role restriction currently enforced

Routes:

- `GET /books` — list all books
- `POST /books` — create a book
- `GET /books/{book_id}` — fetch one book
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

Permission:

- authenticated user required
- no extra role restriction currently enforced

Routes:

- `GET /reservations`
- `POST /reservations`
- `GET /reservations/{reservation_id}`
- `DELETE /reservations/{reservation_id}`

Create body:

```json
{
  "library_id": 1,
  "book_id": 10
}
```

Current behavior:

- the reservation creator is intended to become the reader automatically

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

- `200` — updated user
- `403` — permission denied
- `404` — user not found
- `422` — validation error

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
