from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _


NAME_ALLOWED_PUNCTUATION = {" ", "-", "'", "’"}
SPECIAL_CHARACTER_RE = re.compile(r"[^A-Za-z0-9\s]")


def normalise_email_value(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().lower()


def validate_email_value(value: str) -> str:
    normalized = normalise_email_value(value)
    validate_email(normalized)
    return normalized


def validate_person_name(value: str, *, field_label: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValidationError(_("%(field)s cannot be empty or whitespace only."), params={"field": field_label})

    if not any(char.isalpha() for char in normalized):
        raise ValidationError(_("%(field)s must contain at least one letter."), params={"field": field_label})

    invalid_characters = {
        char for char in normalized if not (char.isalpha() or char in NAME_ALLOWED_PUNCTUATION)
    }
    if invalid_characters:
        raise ValidationError(
            _("%(field)s contains unsupported characters."),
            params={"field": field_label},
        )

    return normalized


class UppercasePasswordValidator:
    def validate(self, password: str, user=None) -> None:
        if not any(char.isupper() for char in password):
            raise ValidationError(
                _("This password must contain at least one uppercase letter."),
                code="password_no_uppercase",
            )

    def get_help_text(self) -> str:
        return _("Your password must contain at least one uppercase letter.")


class DigitPasswordValidator:
    def validate(self, password: str, user=None) -> None:
        if not any(char.isdigit() for char in password):
            raise ValidationError(
                _("This password must contain at least one digit."),
                code="password_no_digit",
            )

    def get_help_text(self) -> str:
        return _("Your password must contain at least one digit.")


class SpecialCharacterPasswordValidator:
    def validate(self, password: str, user=None) -> None:
        if not SPECIAL_CHARACTER_RE.search(password):
            raise ValidationError(
                _("This password must contain at least one special character."),
                code="password_no_special",
            )

    def get_help_text(self) -> str:
        return _("Your password must contain at least one special character.")


class NonWhitespacePasswordValidator:
    def validate(self, password: str, user=None) -> None:
        if not password.strip():
            raise ValidationError(
                _("This password cannot be empty or whitespace only."),
                code="password_whitespace_only",
            )

    def get_help_text(self) -> str:
        return _("Your password cannot be empty or whitespace only.")