from datetime import datetime
from django.core.validators import EmailValidator
from ninja import Field, Schema
from app.domain.models import Voivodeship

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
    isbn: str | None = None
    publisher: str | None = None
    publication_date: datetime | None = None
    page_count: int | None = None
    cover_url: str | None = None
    language: str | None = None
    authors: list[AuthorSchemaOut]

class BookSchemaIn(Schema):
    title: str
    isbn: str
    publisher: str | None = None
    publication_date: datetime | None = None
    page_count: int | None = None
    cover_url: str | None = None
    language: str | None = None
    author_ids: list[int]

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
