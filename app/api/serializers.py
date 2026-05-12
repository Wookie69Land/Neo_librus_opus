from datetime import datetime, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from ninja import Field, Schema
from pydantic import computed_field, field_validator

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


class BookLibraryAvailabilitySchema(Schema):
    id: int = Field(..., description="Library identifier.")
    name: str = Field(..., description="Library display name.")
    city: str | None = Field(None, description="Library city.")
    region: int | None = Field(None, description=region_description)
    is_available: bool = Field(..., description="Availability status returned by the latest check.")
    availability_checked_at: datetime = Field(
        ..., description="Timestamp when availability was last checked for this response."
    )
    availability_source: str = Field(..., description="Source that produced the availability result.")


class BookDetailSchemaOut(BookSchemaOut):
    libraries: list[BookLibraryAvailabilitySchema] = Field(
        ..., description="Libraries that currently hold this book, ordered by user region when available."
    )


class BookAvailabilityResponseSchema(Schema):
    book_id: int = Field(..., description="Book identifier.")
    title: str = Field(..., description="Book title.")
    user_region: int | None = Field(None, description=region_description)
    checked_via: str = Field(..., description="Availability provider used to build the response.")
    libraries: list[BookLibraryAvailabilitySchema] = Field(
        ..., description="Libraries holding the book, ordered by region match and then by name."
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


class ReadersListQuery(Schema):
    page: int = 1
    page_size: int = 20


class PaginatedLibraryUserSchema(Schema):
    items: list[LibraryUserSchema]
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

_ACTIVE_STATUSES = frozenset({"pending", "accepted"})
_COMPLETED_STATUSES = frozenset({"closed"})
_UNFULFILLED_STATUSES = frozenset({"expired", "rejected", "cancelled"})

# Must match the cyclic task constants in app/tasks/reservations.py
_PENDING_EXPIRY_HOURS = 48
_ACCEPTED_CLOSE_DAYS = 3


class ReservationSchemaOut(Schema):
    id: int
    status: StatusSchemaOut
    start_time: datetime
    end_time: datetime | None = None
    updated_at: datetime
    reader: LibraryUserSchema
    librarian: LibraryUserSchema | None = None
    library: LibrarySchemaOut
    book: BookSchemaOut

    @computed_field
    @property
    def state(self) -> str:
        name = self.status.name.lower()
        if name in _ACTIVE_STATUSES:
            return "active"
        if name in _COMPLETED_STATUSES:
            return "completed"
        return "unfulfilled"

    @computed_field
    @property
    def planned_end_time(self) -> datetime | None:
        name = self.status.name.lower()
        if name == "pending":
            return self.updated_at + timedelta(hours=_PENDING_EXPIRY_HOURS)
        if name == "accepted":
            return self.updated_at + timedelta(days=_ACCEPTED_CLOSE_DAYS)
        return None

class ReservationSchemaIn(Schema):
    library_id: int
    book_id: int


class ReservationUpdateSchema(Schema):
    status_id: int


class ReservationListQuery(Schema):
    page: int = 1
    page_size: int = 20
    status: str | None = None
    library_id: int | None = None


class PaginatedReservationSchemaOut(Schema):
    items: list[ReservationSchemaOut]
    page: int
    page_size: int
    total: int
    total_pages: int

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


class UserUpdateResponseSchema(Schema):
    user: LibraryUserSchema
    token: str | None = Field(
        None,
        description=(
            "Refreshed JWT token. Returned for self-service updates so the client can replace the "
            "current Authorization bearer token."
        ),
    )
