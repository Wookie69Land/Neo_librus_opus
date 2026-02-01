"""Domain models for Neo-Librus: custom User, Book, and Loan.

All models are standard Django models; async ORM operations are provided
by the repository layer in `repository.py`.
"""
from __future__ import annotations

from typing import Optional

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model for Neo-Librus.

    This class extends Django's :class:`AbstractUser` to allow future
    customization. For now it behaves the same but provides a named
    model to reference in :setting:`AUTH_USER_MODEL`.
    """

    bio: Optional[str] = models.TextField(blank=True, null=True)


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
    isbn: Optional[str] = models.CharField(max_length=32, blank=True, null=True)
    copies: int = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "domain"
        ordering = ["title"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.title} by {self.author}"


class Loan(models.Model):
    """Represents a loan of a Book to a User.

    The loan stores the borrower, the book, and timestamps for borrow
    and return. A null `returned_at` indicates the book is still on loan.
    """

    borrower = models.ForeignKey("domain.User", on_delete=models.CASCADE, related_name="loans")
    book = models.ForeignKey("domain.Book", on_delete=models.CASCADE, related_name="loans")
    borrowed_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        app_label = "domain"

    def is_active(self) -> bool:
        """Return True if the loan has not been returned yet."""
        return self.returned_at is None
