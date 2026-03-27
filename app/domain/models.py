"""Domain models for Librarius, updated to the new schema with English field names."""
from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from app.domain.isbn import normalise_isbn, validate_isbn
from app.domain.validators import normalise_email_value, validate_person_name


class Status(models.Model):
    """Model for reservation statuses."""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50,
                            unique=True,
                            verbose_name=_("Status Name"))

    class Meta:
        verbose_name = _("Status")
        verbose_name_plural = _("Statuses")

    def __str__(self):
        return self.name

class Voivodeship(models.IntegerChoices):
    DOLNOSLASKIE = 1, _("dolnośląskie")
    KUJAWSKO_POMORSKIE = 2, _("kujawsko-pomorskie")
    LUBELSKIE = 3, _("lubelskie")
    LUBUSKIE = 4, _("lubuskie")
    LODZKIE = 5, _("łódzkie")
    MALOPOLSKIE = 6, _("małopolskie")
    MAZOWIECKIE = 7, _("mazowieckie")
    OPOLSKIE = 8, _("opolskie")
    PODKARPACKIE = 9, _("podkarpackie")
    PODLASKIE = 10, _("podlaskie")
    POMORSKIE = 11, _("pomorskie")
    SLASKIE = 12, _("śląskie")
    SWIETOKRZYSKIE = 13, _("świętokrzyskie")
    WARMINSKO_MAZURSKIE = 14, _("warmińsko-mazurskie")
    WIELKOPOLSKIE = 15, _("wielkopolskie")
    ZACHODNIOPOMORSKIE = 16, _("zachodniopomorskie")


class IntegrationSource(models.IntegerChoices):
    UNKNOWN = 0, _("Unknown / manual")
    EISBN = 1, _("e-ISBN")
    CURATED_POLISH_TOP100 = 20, _("Curated Polish Top 100")


class LibraryUser(AbstractUser):
    """
    Custom user model for Librarius.

    Inherits from Django's AbstractUser and adds a 'region' field.

    Fields from AbstractUser:
    - id (primary key)
    - first_name
    - last_name
    - username (unique)
    - password (hashed)
    - is_superuser (boolean)
    - email
    - password (hashed)
    - is_staff (boolean)
    - is_active (boolean)
    - date_joined (datetime)
    - last_login (datetime)

    Custom fields:
    - region
    """
    region = models.IntegerField(choices=Voivodeship.choices,
                                 blank=True,
                                 null=True,
                                 verbose_name=_("Region"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Updated"))

    class Meta:
        verbose_name = _("Library User")
        verbose_name_plural = _("Library Users")

    def clean(self) -> None:
        super().clean()
        self.email = normalise_email_value(self.email)
        if self.first_name:
            self.first_name = validate_person_name(self.first_name, field_label="First name")
        if self.last_name:
            self.last_name = validate_person_name(self.last_name, field_label="Last name")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

class Role(models.Model):
    """Model for user roles in a library."""
    id = models.AutoField(primary_key=True,
                             verbose_name=_("Role ID"))
    name = models.CharField(max_length=100,
                            unique=True,
                            verbose_name=_("Role Name"))
    added_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Added At"))

    class Meta:
        verbose_name = _("Role")
        verbose_name_plural = _("Roles")

    def __str__(self):
        return self.name

class Library(models.Model):
    """Represents a library."""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Address"))
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("City"))
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Phone"))
    email = models.EmailField(blank=True, null=True, verbose_name=_("Email"))
    region = models.IntegerField(choices=Voivodeship.choices, blank=True, null=True, verbose_name=_("Region"))
    added_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Added At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Updated"))

    class Meta:
        verbose_name = _("Library")
        verbose_name_plural = _("Libraries")

    def clean(self) -> None:
        super().clean()
        self.email = normalise_email_value(self.email) or None

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Author(models.Model):
    """Represents an author of a book."""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, verbose_name=_("Name"))

    class Meta:
        verbose_name = _("Author")
        verbose_name_plural = _("Authors")

    def __str__(self):
        return self.name

class Book(models.Model):
    """Represents a book."""
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255, verbose_name=_("Title"))
    isbn = models.CharField(
        max_length=20, unique=True, verbose_name=_("ISBN"), validators=[validate_isbn]
    )
    integration_source = models.SmallIntegerField(
        choices=IntegrationSource.choices,
        default=IntegrationSource.UNKNOWN,
        verbose_name=_("Integration Source"),
    )
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("Last Updated"))
    data_source = models.CharField(
        max_length=100, blank=True, null=True, verbose_name=_("Data Source")
    )
    google_id = models.CharField(
        max_length=100, blank=True, null=True, db_index=True,
        verbose_name=_("Google Books ID")
    )
    publisher = models.CharField(
        max_length=255, blank=True, null=True, verbose_name=_("Publisher")
    )
    published_year = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_("Published Year")
    )
    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))
    page_count = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_("Page Count")
    )
    print_type = models.CharField(
        max_length=50, blank=True, null=True, verbose_name=_("Print Type")
    )
    category = models.CharField(
        max_length=511, blank=True, null=True, verbose_name=_("Category")
    )
    cover_url = models.URLField(max_length=1000, blank=True, null=True, verbose_name=_("Cover URL"))
    language = models.CharField(
        max_length=10, blank=True, null=True, verbose_name=_("Language")
    )
    google_checked = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("Google Checked"),
    )
    authors = models.ManyToManyField(
        Author, through='BookAuthor', related_name='books', verbose_name=_("Authors")
    )

    class Meta:
        verbose_name = _("Book")
        verbose_name_plural = _("Books")

    def clean(self) -> None:
        super().clean()
        self.isbn = normalise_isbn(self.isbn)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class BookAuthor(models.Model):
    """Through model for the many-to-many relationship between Book and Author."""
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('author', 'book')
        verbose_name = _("Book Author")
        verbose_name_plural = _("Book Authors")

class LibraryBook(models.Model):
    """Through model connecting Books and Libraries, indicating book availability."""
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    library = models.ForeignKey(Library, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True, verbose_name=_("Is Available"))
    added_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Added At"))

    class Meta:
        unique_together = ('book', 'library')
        verbose_name = _("Book in Library")
        verbose_name_plural = _("Books in Libraries")

class Reservation(models.Model):
    """Represents a book reservation."""
    id = models.AutoField(primary_key=True)
    status = models.ForeignKey(Status, on_delete=models.PROTECT, verbose_name=_("Status"))
    start_time = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Reservation Start Time")
    )
    end_time = models.DateTimeField(
        blank=True, null=True, verbose_name=_("Reservation End Time")
    )
    reader = models.ForeignKey(
        LibraryUser, related_name='reservations_as_reader', on_delete=models.CASCADE,
        verbose_name=_("Reader")
    )
    librarian = models.ForeignKey(
        LibraryUser, related_name='reservations_as_librarian', blank=True,
        null=True, on_delete=models.SET_NULL, verbose_name=_("Librarian")
    )
    library = models.ForeignKey(
        Library, on_delete=models.CASCADE, verbose_name=_("Library")
    )
    book = models.ForeignKey(Book, on_delete=models.CASCADE, verbose_name=_("Book"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Updated"))

    class Meta:
        verbose_name = _("Reservation")
        verbose_name_plural = _("Reservations")

    def __str__(self):
        return f"Reservation {self.id} for '{self.book.title}'"

class LibraryAdmin(models.Model):
    """Through model for library administrators and their roles."""
    library = models.ForeignKey(Library, on_delete=models.CASCADE)
    user = models.ForeignKey(LibraryUser, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    added_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Added At"))

    class Meta:
        unique_together = ('library', 'user')
        verbose_name = _("Library Administrator")
        verbose_name_plural = _("Library Administrators")


class SessionToken(models.Model):
    """Model for storing user session tokens in the database."""
    id = models.AutoField(primary_key=True)
    key = models.CharField(max_length=700, unique=True)
    user = models.OneToOneField(
        LibraryUser, related_name='auth_token', on_delete=models.CASCADE, verbose_name=_("User")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    class Meta:
        verbose_name = _("Session Token")
        verbose_name_plural = _("Session Tokens")

    def __str__(self):
        return self.key


class CyclicTaskReport(models.Model):
    """Stores recent execution results for scheduled and manually triggered cyclic tasks."""

    id = models.AutoField(primary_key=True)
    task_name = models.CharField(max_length=100, db_index=True, verbose_name=_("Task Name"))
    status = models.CharField(max_length=20, verbose_name=_("Status"))
    started_at = models.DateTimeField(verbose_name=_("Started At"))
    finished_at = models.DateTimeField(verbose_name=_("Finished At"))
    duration_ms = models.PositiveIntegerField(default=0, verbose_name=_("Duration (ms)"))
    payload = models.JSONField(default=dict, blank=True, verbose_name=_("Payload"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    class Meta:
        ordering = ["-started_at", "-id"]
        verbose_name = _("Cyclic Task Report")
        verbose_name_plural = _("Cyclic Task Reports")

    def __str__(self) -> str:
        return f"{self.task_name} [{self.status}]"
