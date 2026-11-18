"""Keeping rejected submissions as drafts (never as complaints)."""
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from departments.models import Area, Ward

from ..models import SubmissionAttempt
from ..validators import normalize_text, validate_image_upload
from .submission import sanitize_image

logger = logging.getLogger("routelync")
MAX_OPEN = 20


def _decimal(value):
    try:
        return Decimal(str(value).strip()).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError):
        return None


def record_rejection(citizen, form, result, attempt=None):
    """Save what the citizen typed (and a safe copy of the photo) so they can fix the description and retry.
    Returns the attempt, or None if the daily limit for drafts was reached (the form still shows the error)."""
    if attempt is None:
        since = timezone.now() - timedelta(days=1)
        if SubmissionAttempt.objects.filter(citizen=citizen, created_at__gte=since).count() >= settings.MAX_ATTEMPTS_PER_DAY:
            return None
        attempt = SubmissionAttempt(citizen=citizen)
    data = form.data
    attempt.title = normalize_text(data.get("title", ""))[:120]
    attempt.description = normalize_text(data.get("description", ""))[:2000]
    area = data.get("area", "")
    attempt.area = Area.objects.filter(pk=int(area)).first() if str(area).isdigit() else None
    ward_number = form.cleaned_data.get("ward_number")
    attempt.ward = (Ward.objects.filter(area=attempt.area, number=ward_number).first()
                    if attempt.area and ward_number else None)
    attempt.ward_text = (str(ward_number) if ward_number else normalize_text(data.get("ward", "")))[:100]
    if attempt.ward:
        attempt.ward_text = ""
    attempt.street = normalize_text(data.get("street", ""))[:150]
    attempt.landmark = normalize_text(data.get("landmark", ""))[:150]
    attempt.building = normalize_text(data.get("building", ""))[:150]
    attempt.address_text = normalize_text(data.get("address_text", ""))[:300]
    attempt.latitude, attempt.longitude = _decimal(data.get("latitude")), _decimal(data.get("longitude"))
    attempt.reason_code, attempt.reason_label = result.verdict.value, result.label
    attempt.message = result.message[:400]

    upload = form.files.get("image")
    if upload is not None:
        try:
            validate_image_upload(upload)
            if attempt.image:
                attempt.image.delete(save=False)
            attempt.image = sanitize_image(upload)
        except (ValidationError, OSError):
            pass                                            # a bad photo is reported by the form itself; keep the old one
    attempt.save()
    for old in SubmissionAttempt.objects.filter(citizen=citizen).order_by("-updated_at")[MAX_OPEN:]:
        discard_attempt(old)
    return attempt


def discard_attempt(attempt):
    if attempt.image:
        attempt.image.delete(save=False)
    attempt.delete()


def purge_old_attempts(days=None) -> int:
    cutoff = timezone.now() - timedelta(days=days or settings.ATTEMPT_RETENTION_DAYS)
    old = list(SubmissionAttempt.objects.filter(updated_at__lt=cutoff))
    for attempt in old:
        discard_attempt(attempt)
    return len(old)
