from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


ISBN_DIGIT_RE = re.compile(r"[^0-9Xx]")


def normalise_isbn(value: str | None) -> str:
    if value is None:
        return ""
    return ISBN_DIGIT_RE.sub("", value).upper()


def is_valid_isbn10(value: str) -> bool:
    if len(value) != 10 or not re.fullmatch(r"\d{9}[\dX]", value):
        return False
    total = 0
    for index, char in enumerate(value[:9], start=1):
        total += index * int(char)
    check_digit = 10 if value[-1] == "X" else int(value[-1])
    total += 10 * check_digit
    return total % 11 == 0


def is_valid_isbn13(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    total = 0
    for index, char in enumerate(value[:12]):
        factor = 1 if index % 2 == 0 else 3
        total += int(char) * factor
    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(value[-1])


def validate_isbn(value: str) -> None:
    normalised = normalise_isbn(value)
    if not normalised:
        raise ValidationError(_("ISBN cannot be empty."))
    if is_valid_isbn10(normalised) or is_valid_isbn13(normalised):
        return
    raise ValidationError(_("Enter a valid ISBN-10 or ISBN-13."))
