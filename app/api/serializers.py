from datetime import datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from ninja import Field, Schema
from pydantic import field_validator

from app.domain.languages import get_language_display
from app.domain.models import Voivodeship
from app.domain.validators import validate_email_value, validate_person_name

region_description = "Region as an integer. Available choices:\\n" + "\\n".join(
    [f"{choice.value} - {choice.label}" for choice in Voivodeship]
)

class StatusSchemaOut(Schema):
    id: int
    name: str

class StatusSchemaIn(Schema):
    name: str

class RoleSchemaOut(Schema):
    id: int
    name: str

class RoleSchemaIn(Schema):
    name: str

class LibraryUserSchema(Schema):
    id: int
    username: str
    email: str = Field(..., description="User's email address.")
    first_name: str
    last_name: str
    region: int | None = Field(None, description=region_description)
    is_active: bool
    date_joined: datetime
    last_login: datetime | None = None

class RegisterSchema(Schema):
    email: str = Field(..., description="A valid email address.")
    password: str
    first_name: str
    last_name: str
    region: int | None = Field(None, description=region_description)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        try:
            return validate_email_value(value)
        except DjangoValidationError as exc:
            raise ValueError("Enter a valid email address.") from exc

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, value: str) -> str:
        try:
            return validate_person_name(value, field_label="First name")
        except DjangoValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, value: str) -> str:
        try:
            return validate_person_name(value, field_label="Last name")
        except DjangoValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc

    @field_validator("password")
    @classmethod
    def validate_register_password(cls, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc
        return value

class LoginSchema(Schema):
    login: str
    password: str

class LogoutSchema(Schema):
    token: str

class AuthorSchemaOut(Schema):
    id: int
    name: str

class AuthorSchemaIn(Schema):
    name: str

class BookSchemaOut(Schema):
    id: int
    title: str
    integration_source: int
    data_source: str | None = None
    google_id: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    published_year: int | None = None
    description: str | None = None
    page_count: int | None = None
    print_type: str | None = None
    category: str | None = None
    cover_url: str | None = None
    language: str | None = None
    language_display: str | None = None
    last_updated: datetime
    authors: list[AuthorSchemaOut]

    @staticmethod
    def from_book(book, authors: list[AuthorSchemaOut]) -> "BookSchemaOut":
        return BookSchemaOut(
            id=book.id,
            title=book.title,
            integration_source=book.integration_source,
            data_source=book.data_source,
            google_id=book.google_id,
            isbn=book.isbn,
            publisher=book.publisher,
            published_year=book.published_year,
            description=book.description,
            page_count=book.page_count,
            print_type=book.print_type,
            category=book.category,
            cover_url=book.cover_url,
            language=book.language,
            language_display=get_language_display(book.language),
            last_updated=book.last_updated,
            authors=authors,
        )

class BookSchemaIn(Schema):
    title: str
    isbn: str
    integration_source: int = 0
    data_source: str | None = None
    google_id: str | None = None
    publisher: str | None = None
    published_year: int | None = None
    description: str | None = None
    page_count: int | None = None
    print_type: str | None = None
    category: str | None = None
    cover_url: str | None = None
    language: str | None = None
    author_ids: list[int]


class PaginatedBookSchemaOut(Schema):
    items: list[BookSchemaOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class BookLanguageSchema(Schema):
    code: str
    display: str

class LibrarySchemaOut(Schema):
    id: int
    name: str
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None
    region: int | None = Field(None, description=region_description)

class LibrarySchemaIn(Schema):
    name: str
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None
    region: int | None = Field(None, description=region_description)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            return None
        try:
            return validate_email_value(value)
        except DjangoValidationError as exc:
            raise ValueError("Enter a valid email address.") from exc

class LibraryBookSchema(Schema):
    book: BookSchemaOut
    library: LibrarySchemaOut
    is_available: bool

class ReservationSchemaOut(Schema):
    id: int
    status: StatusSchemaOut
    start_time: datetime
    end_time: datetime | None = None
    reader: LibraryUserSchema
    librarian: LibraryUserSchema | None = None
    library: LibrarySchemaOut
    book: BookSchemaOut

class ReservationSchemaIn(Schema):
    library_id: int
    book_id: int


class ReservationUpdateSchema(Schema):
    status_id: int | None = None
    end_time: datetime | None = None
    librarian_id: int | None = None

class UserReservationSchemaOut(Schema):
    id: int
    status: StatusSchemaOut
    start_time: datetime
    end_time: datetime | None = None
    library: LibrarySchemaOut
    book: BookSchemaOut

class LibraryAdminInfoSchema(Schema):
    library: LibrarySchemaOut
    role: RoleSchemaOut

class UserDetailSchema(Schema):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    region: int | None = None
    is_active: bool
    date_joined: datetime
    last_login: datetime | None = None
    library_roles: list[LibraryAdminInfoSchema]
    active_reservations: list[UserReservationSchemaOut]

class UserUpdateSchema(Schema):
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    region: int | None = None
    password: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            return None
        try:
            return validate_email_value(value)
        except DjangoValidationError as exc:
            raise ValueError("Enter a valid email address.") from exc

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_person_name(value, field_label="First name")
        except DjangoValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_person_name(value, field_label="Last name")
        except DjangoValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc

    @field_validator("password")
    @classmethod
    def validate_update_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc
        return value
