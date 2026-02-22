"""Domain models for Librarius: custom User, Book, and Reservation.

All models are standard Django models; async ORM operations are provided
by the repository layer in `repository.py`.

AbstractUser is Django's built-in user model that we extend with additional fields as needed.
By default, it includes fields:
- username
- email
- password
- first_name
- last_name
- is_staff
- is_active
- date_joined
- last_login
We can add custom fields (e.g. bio) to store additional user information.
"""
from __future__ import annotations

from typing import Optional

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now, timedelta
from django.utils.translation import gettext_lazy as _

class UKDCategory(models.Model):
    """Represents a UKD category for library classification."""

    symbol = models.CharField(max_length=10, verbose_name=_("Symbol"))
    nazwa_dzialu = models.CharField(max_length=255, verbose_name=_("Nazwa działu"))
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="subcategories",
        verbose_name=_("Kategoria nadrzędna")
    )

    class Meta:
        verbose_name = _("Kategoria UKD")
        verbose_name_plural = _("Kategorie UKD")

    def __str__(self):
        return f"{self.symbol} - {self.nazwa_dzialu}"

class CustomUser(AbstractUser):
    """Custom user model for Neo-Librus."""
    bio = models.TextField(blank=True, null=True, verbose_name=_("Biografia"))
    
    class Meta:
        verbose_name = _("Użytkownik")
        verbose_name_plural = _("Użytkownicy")

class Library(models.Model):
    """Represents a library branch."""
    name = models.CharField(max_length=255, verbose_name=_("Nazwa biblioteki"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Opis biblioteki"))


    class Meta:
        verbose_name = _("Biblioteka")
        verbose_name_plural = _("Biblioteki")

    def __str__(self):
        return self.name

class Branch(models.Model):
    """Represents a library branch."""
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="branches"),
    name = models.CharField(max_length=255, verbose_name=_("Nazwa oddziału"))
    street = models.TextField(verbose_name=_("Ulica"))
    city = models.CharField(max_length=255, verbose_name=_("Miasto"))
    postal_code = models.CharField(max_length=20, verbose_name=_("Kod pocztowy"))
    phone = models.CharField(max_length=20, verbose_name=_("Telefon"))
    email = models.EmailField(verbose_name=_("Email"))
    added_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Data dodania"))
    additional_info = models.TextField(blank=True, null=True, verbose_name=_("Dodatkowe informacje"))

    class Meta:
        verbose_name = _("Oddział biblioteki")
        verbose_name_plural = _("Oddziały biblioteki")

    def __str__(self):
        return self.name

class LibrarianProfile(models.Model):
    """Profile for librarians."""
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="librarian_profile")
    libraries = models.ManyToManyField(Library, related_name="librarians", verbose_name=_("Biblioteki"))

    class Meta:
        verbose_name = _("Profil bibliotekarza")
        verbose_name_plural = _("Profile bibliotekarzy")

    def __str__(self):
        return f"Bibliotekarz: {self.user.username}"

class AdminProfile(models.Model):
    """Profile for system administrators."""
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="admin_profile")

    class Meta:
        verbose_name = _("Profil administratora")
        verbose_name_plural = _("Profile administratorów")

    def __str__(self):
        return f"Administrator: {self.user.username}"

class Book(models.Model):
    """Represents a library book.

    Attributes:
        title: The display title of the book.
        author: The author string.
        isbn: Optional ISBN identifier.
        copies: Number of copies available.
    """

    title: str = models.CharField(max_length=255)
    author: str = models.CharField(max_length=255)

    ukd_categories = models.ManyToManyField(
        UKDCategory, related_name="books", verbose_name=_("Kategorie UKD")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "domain"
        ordering = ["title"]

    def __str__(self) -> str:
        return f"{self.title} by {self.author}"


class Edition(models.Model):
    """Represents a specific edition of a book."""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="editions", verbose_name=_("Książka"))
    isbn = models.CharField(max_length=32, verbose_name=_("ISBN"))
    year = models.PositiveIntegerField(verbose_name=_("Rok wydania"))
    publisher = models.CharField(max_length=255, verbose_name=_("Wydawnictwo"))
    total_copies = models.PositiveIntegerField(verbose_name=_("Liczba egzemplarzy"))
    available_copies = models.PositiveIntegerField(verbose_name=_("Dostępne egzemplarze"))
    info = models.TextField(blank=True, null=True, verbose_name=_("Dodatkowe informacje"))

    class Meta:
        verbose_name = _("Edycja książki")
        verbose_name_plural = _("Edycje książek")

    def __str__(self):
        return f"{self.isbn} ({self.year})"

    def reserve_copy(self):
        if self.available_copies > 0:
            self.available_copies -= 1
            self.save()
            return True
        return False

    def release_copy(self):
        if self.available_copies < self.total_copies:
            self.available_copies += 1
            self.save()

class Reservation(models.Model):
    """Represents a reservation of a book edition by a user."""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="reservations", verbose_name=_("Użytkownik"))
    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="reservations", verbose_name=_("Edycja książki"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Data utworzenia"))
    expires_at = models.DateTimeField(verbose_name=_("Data wygaśnięcia"))

    class Meta:
        verbose_name = _("Rezerwacja")
        verbose_name_plural = _("Rezerwacje")

    def save(self, *args, **kwargs):
        if not self.pk:  # Only check availability on creation
            if not self.edition.reserve_copy():
                raise ValueError("Brak dostępnych egzemplarzy tej edycji.")
            self.expires_at = now() + timedelta(hours=48)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.edition.release_copy()
        super().delete(*args, **kwargs)

