"""
Validators for complaint input: free text, GPS coordinates and uploaded images.

The text checks are HEURISTICS to stop obviously meaningless submissions ("test", "aaaaaaa",
keyboard mashing, link spam). They cannot judge truthfulness; the real quality gate is the
human verification step for low-confidence complaints (Phase 6).
"""
import os
import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

# ----------------------------------------------------------------------------- text
_TOKEN = re.compile(r"[^\W\d_]+")                      # runs of letters (any script)
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_KEYBOARD_ROWS = ("asdf", "qwer", "zxcv", "hjkl", "sdfg", "wert", "xcvb")
_PLACEHOLDER_WORDS = {
    "test", "tests", "testing", "hello", "hi", "hey", "abc", "abcd", "asdf", "qwerty", "xyz",
    "demo", "sample", "blah", "lorem", "ipsum", "none", "nothing", "na", "dummy", "check",
}


def normalize_text(value: str) -> str:
    """Trim, drop control characters, collapse runs of spaces/tabs and blank lines."""
    value = "".join(ch for ch in (value or "") if ch == "\n" or ch.isprintable())
    value = re.sub(r"[^\S\n]+", " ", value)
    value = re.sub(r" ?\n ?", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _gibberish_token(token: str) -> bool:
    t = token.lower()
    if not t.isascii():           # rules below are only meaningful for Latin-script words
        return False
    if re.search(r"(.)\1{3,}", t):                      # aaaa
        return True
    if len(t) >= 5 and not re.search(r"[aeiouy]", t):   # no vowel at all
        return True
    if re.search(r"[^aeiouy]{7,}", t):                  # very long consonant run
        return True
    return any(row in t for row in _KEYBOARD_ROWS)


def validate_meaningful_text(value, *, label, min_chars, max_chars, min_words=1):
    """Raise ValidationError unless `value` (already normalised) looks like real writing."""
    if len(value) < min_chars:
        raise ValidationError(f"{label} is too short. Please write at least {min_chars} characters.", code="too_short")
    if len(value) > max_chars:
        raise ValidationError(f"{label} is too long (maximum {max_chars} characters).", code="too_long")
    if _URL.search(value):
        raise ValidationError(f"Links are not allowed in the {label.lower()}.", code="has_link")

    compact = re.sub(r"\s", "", value)
    letters = sum(ch.isalpha() for ch in compact)
    if letters / max(len(compact), 1) < 0.6:
        raise ValidationError(f"{label} must mainly contain words, not numbers or symbols.", code="not_words")

    tokens = [t.lower() for t in _TOKEN.findall(value)]
    meaningful = [t for t in tokens if t not in _PLACEHOLDER_WORDS]
    if len(tokens) < min_words:
        raise ValidationError(f"{label} is too short: please write at least {min_words} words (you wrote {len(tokens)}).", code="too_few_words")
    if len(meaningful) < min_words:
        raise ValidationError(f"Please describe the issue in more detail ({label.lower()} looks like a placeholder).",
                              code="placeholder")
    if min_words >= 3 and len(set(meaningful)) < 3:
        raise ValidationError(f"{label} repeats the same words. Please describe the problem clearly.", code="repetitive")
    if tokens and sum(_gibberish_token(t) for t in tokens) / len(tokens) > 0.4:
        raise ValidationError(f"{label} does not look like meaningful text. Please rewrite it.", code="gibberish")


def validate_title(value):
    validate_meaningful_text(value, label="Title", min_chars=5, max_chars=120, min_words=1)


def validate_description(value):
    """A citizen's description is COMPULSORY and must be real text of at least COMPLAINT_MIN_WORDS words.
    The classifier reads text only, so a photo or a one-word message gives it nothing to work with."""
    validate_meaningful_text(value, label="Description", min_chars=20, max_chars=2000, min_words=settings.COMPLAINT_MIN_WORDS)


def validate_training_text(value):
    """Training examples keep a lower bar (4 words): short, clear examples are useful to the model."""
    validate_meaningful_text(value, label="Description", min_chars=20, max_chars=2000, min_words=4)


def validate_street(value):
    validate_meaningful_text(value, label="Street name", min_chars=3, max_chars=150, min_words=1)


def validate_address(value):
    validate_meaningful_text(value, label="Address", min_chars=10, max_chars=300, min_words=2)


# ----------------------------------------------------------------------------- GPS
def validate_latitude(value):
    if value is not None and not (Decimal(-90) <= value <= Decimal(90)):
        raise ValidationError("Latitude must be between -90 and 90.", code="lat_range")


def validate_longitude(value):
    if value is not None and not (Decimal(-180) <= value <= Decimal(180)):
        raise ValidationError("Longitude must be between -180 and 180.", code="lon_range")


# ----------------------------------------------------------------------------- image
EXT_TO_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


def validate_image_upload(upload):
    """
    Do not trust the file name or the browser-supplied content type. We check size, then open the
    file with Pillow to learn its REAL format, dimensions and integrity, and require the extension
    to agree with the content.
    """
    max_bytes = int(settings.MAX_IMAGE_SIZE_MB * 1024 * 1024)
    if upload.size == 0:
        raise ValidationError("The uploaded file is empty.", code="empty")
    if upload.size > max_bytes:
        raise ValidationError(f"Image is too large. Maximum size is {settings.MAX_IMAGE_SIZE_MB} MB.", code="too_big")

    ext = os.path.splitext(upload.name or "")[1].lower()
    if ext not in EXT_TO_FORMAT:
        raise ValidationError("Only JPG, JPEG, PNG or WEBP images are allowed.", code="bad_extension")

    try:
        upload.seek(0)
        with Image.open(upload) as img:
            real_format = img.format
            width, height = img.size            # read from the header, before decoding pixels
            if width * height > settings.MAX_IMAGE_PIXELS_ALLOWED:
                raise ValidationError("Image dimensions are too large.", code="too_many_pixels")
            img.verify()                        # structural integrity check
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ValidationError("This file is not a valid image.", code="not_image")
    finally:
        upload.seek(0)

    if real_format not in settings.ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Only JPG, JPEG, PNG or WEBP images are allowed.", code="bad_format")
    if EXT_TO_FORMAT[ext] != real_format:
        raise ValidationError("The file extension does not match the image content.", code="ext_mismatch")
