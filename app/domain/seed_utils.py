from __future__ import annotations

import re
from typing import Iterable

from app.domain.models import Author, Book, BookAuthor


def normalise_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def capitalise_compound_word(value: str) -> str:
    parts = re.split(r"([\-'.’/])", value)
    return "".join(part.capitalize() if part and part not in "-'.’/" else part for part in parts)


def normalise_capitalisation(value: str) -> str:
    collapsed = normalise_whitespace(value)
    if not collapsed:
        return ""
    return " ".join(capitalise_compound_word(part) for part in collapsed.split(" "))


def normalise_author_name(value: str) -> str:
    return normalise_capitalisation(value)


def normalise_email(value: str | None) -> str | None:
    if not value:
        return None
    email = normalise_whitespace(value).lower()
    return email or None


def normalise_phone(value: str | None) -> str | None:
    if not value:
        return None
    phone = normalise_whitespace(value)
    return phone or None


def find_or_create_author(name: str) -> Author:
    normalised_name = normalise_author_name(name)
    author = Author.objects.filter(name__iexact=normalised_name).first()
    if author:
        if author.name != normalised_name:
            author.name = normalised_name
            author.save(update_fields=["name"])
        return author
    return Author.objects.create(name=normalised_name)


def sync_book_authors(book: Book, author_names: Iterable[str]) -> bool:
    desired_author_ids: list[int] = []
    for author_name in author_names:
        author = find_or_create_author(author_name)
        if author.id not in desired_author_ids:
            desired_author_ids.append(author.id)

    current_author_ids = set(
        BookAuthor.objects.filter(book=book).values_list("author_id", flat=True)
    )
    desired_author_ids_set = set(desired_author_ids)

    removed = BookAuthor.objects.filter(
        book=book,
        author_id__in=current_author_ids - desired_author_ids_set,
    ).delete()[0]

    added = 0
    for author_id in desired_author_ids:
        _, was_created = BookAuthor.objects.get_or_create(book=book, author_id=author_id)
        if was_created:
            added += 1

    return bool(removed or added)


def apply_field_updates(instance, field_values: dict[str, object]) -> list[str]:
    changed_fields: list[str] = []
    for field_name, field_value in field_values.items():
        if getattr(instance, field_name) != field_value:
            setattr(instance, field_name, field_value)
            changed_fields.append(field_name)
    return changed_fields


def prune_orphan_authors() -> int:
    deleted_count, _ = Author.objects.filter(books__isnull=True).delete()
    return deleted_count
