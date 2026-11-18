"""Shared validators. Complaint-specific validators (text, GPS, image) arrive in Phase 4."""
from django.core.validators import RegexValidator

# Indian mobile number: 10 digits starting with 6-9. Stored digits-only.
mobile_number_validator = RegexValidator(
    regex=r"^[6-9]\d{9}$",
    message="Enter a valid 10-digit Indian mobile number (digits only, starting with 6-9).",
    code="invalid_mobile",
)


import re

from django.core.exceptions import ValidationError

_NAME_FORBIDDEN = re.compile(r"[\d_@#$%^&*()+=\[\]{}|\\<>/?~`!;:\"]")


def validate_person_name(value: str) -> None:
    """Letters (any script), spaces, dots, apostrophes and hyphens only; 2+ characters."""
    value = (value or "").strip()
    if len(value) < 2:
        raise ValidationError("Enter your full name (at least 2 characters).", code="name_short")
    if _NAME_FORBIDDEN.search(value):
        raise ValidationError("Name may contain only letters, spaces, dots, apostrophes and hyphens.", code="name_chars")
