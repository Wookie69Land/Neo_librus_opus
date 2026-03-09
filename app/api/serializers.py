from datetime import datetime

from ninja import Schema


class StatusSchema(Schema):
    id: int
    name: str

class RoleSchema(Schema):
    id: int
    name: str

class LibraryUserSchema(Schema):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    region: str | None = None
    is_active: bool
    date_joined: datetime
    last_login: datetime | None = None

class RegisterSchema(Schema):
    email: str
    password: str
    first_name: str
    last_name: str
    region: str | None = None

class LoginSchema(Schema):
    login: str
    password: str

class AuthorSchema(Schema):
    id: int
    name: str

class BookSchemaOut(Schema):
    id: int
    title: str
    isbn: str | None = None
    publisher: str | None = None
    publication_date: datetime | None = None
    page_count: int | None = None
    cover_url: str | None = None
    language: str | None = None
    authors: list[AuthorSchema]

class BookSchemaIn(Schema):
    title: str
    isbn: str | None = None
    publisher: str | None = None
    publication_date: datetime | None = None
    page_count: int | None = None
    cover_url: str | None = None
    language: str | None = None
    author_ids: list[int]

class LibrarySchema(Schema):
    id: int
    name: str
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None
    region: str | None = None

class LibraryBookSchema(Schema):
    book: BookSchemaOut
    library: LibrarySchema
    is_available: bool

class ReservationSchemaOut(Schema):
    id: int
    status: StatusSchema
    start_time: datetime
    end_time: datetime | None = None
    reader: LibraryUserSchema
    librarian: LibraryUserSchema | None = None
    library: LibrarySchema
    book: BookSchemaOut

class ReservationSchemaIn(Schema):
    library_id: int
    book_id: int
