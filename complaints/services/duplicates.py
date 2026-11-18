"""
Possible-duplicate detection.

A new complaint is compared with recent OPEN complaints in the same ward using cosine similarity of the
cleaned text (single words, damped term frequencies). Inverse-document-frequency weighting is deliberately
NOT used: with only a handful of candidates it would depend on whichever other complaints happen to be
nearby, so the same pair could score differently from day to day. On sample pairs the score separated true
repeats (0.74 to 0.81) from different problems on the same street (0.18 to 0.55). The bar is lower when the street matches or the GPS points are close, and higher when
only the ward matches. A match only creates a DuplicateFlag; a person decides what it means.
"""
import logging
import math
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from sklearn.feature_extraction.text import TfidfVectorizer

from audit.services import log_action
from ml_engine.preprocessing import preprocess_text, whitespace_tokens

from ..models import ACTIVE_STATUSES, Complaint, ComplaintStatus as S, DuplicateFlag, DuplicateStatus
from .errors import WorkflowError

logger = logging.getLogger("routelync")
MAX_CANDIDATES = 200
MAX_FLAGS = 3
_OPEN = tuple(ACTIVE_STATUSES) + (S.NEEDS_VERIFICATION,)


def _metres(a, b) -> float:
    """Great-circle distance between two (lat, lng) points."""
    (lat1, lon1), (lat2, lon2) = [(float(x), float(y)) for x, y in (a, b)]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _street_key(location) -> str:
    return " ".join((location.street or "").lower().split())


def _text(c) -> str:
    return preprocess_text(f"{c.title}. {c.description}")


def find_possible_duplicates(complaint):
    """Returns [(older_complaint, similarity, reason)], best first."""
    loc = complaint.location
    if not loc.ward_id and not (loc.area_id and loc.street):
        return []
    cutoff = complaint.created_at - timedelta(days=settings.DUPLICATE_WINDOW_DAYS)
    candidates_qs = Complaint.objects.filter(status__in=_OPEN, created_at__gte=cutoff, created_at__lt=complaint.created_at)
    if loc.ward_id:
        candidates_qs = candidates_qs.filter(location__ward_id=loc.ward_id)
    else:
        candidates_qs = candidates_qs.filter(location__area_id=loc.area_id, location__street__iexact=loc.street)
    candidates = list(candidates_qs.exclude(pk=complaint.pk).select_related("location").order_by("-created_at")[:MAX_CANDIDATES])
    mine = _text(complaint)
    if not candidates or not mine:
        return []
    texts = [mine] + [_text(c) for c in candidates]
    try:
        matrix = TfidfVectorizer(ngram_range=(1, 1), use_idf=False, sublinear_tf=True, lowercase=False, tokenizer=whitespace_tokens,
                                 token_pattern=None).fit_transform(texts)
    except ValueError:                                  # no usable words at all
        return []
    scores = (matrix[1:] @ matrix[0].T).toarray().ravel()      # rows are L2-normalised: dot product = cosine

    found = []
    for other, score in zip(candidates, scores):
        reason = "same ward" if loc.ward_id else "same area and street"
        if _street_key(other.location) == _street_key(loc):
            reason = "same street"
        elif loc.has_gps and other.location.has_gps and _metres((loc.latitude, loc.longitude), (other.location.latitude, other.location.longitude)) <= settings.DUPLICATE_NEARBY_METRES:
            reason = "nearby location"
        needed = settings.DUPLICATE_THRESHOLD_WARD if reason == "same ward" else settings.DUPLICATE_THRESHOLD_NEARBY
        if score >= needed:
            found.append((other, float(min(score, 1.0)), reason))
    return sorted(found, key=lambda t: -t[1])[:MAX_FLAGS]


def flag_possible_duplicates(complaint) -> int:
    """Create flags for review. Never raises: a failure here must not disturb routing."""
    try:
        with transaction.atomic():
            created = 0
            for other, score, reason in find_possible_duplicates(complaint):
                _, new = DuplicateFlag.objects.get_or_create(complaint=complaint, possible_duplicate_of=other,
                                                             defaults={"similarity": score, "reason": reason})
                created += new
            return created
    except Exception:  # noqa: BLE001
        logger.exception("Duplicate check failed for %s", complaint.reference)
        return 0


@transaction.atomic
def review_duplicate(flag: DuplicateFlag, *, actor, is_duplicate: bool) -> str:
    """A person decides. Confirming rejects the NEWER complaint (if it has not been worked on) and tells the citizen."""
    flag = DuplicateFlag.objects.select_for_update().select_related("complaint", "possible_duplicate_of").get(pk=flag.pk)
    if flag.status != DuplicateStatus.PENDING:
        raise WorkflowError("This suspected duplicate has already been reviewed.")
    flag.reviewed_by, flag.reviewed_at = actor, timezone.now()
    new, old = flag.complaint, flag.possible_duplicate_of
    if not is_duplicate:
        flag.status = DuplicateStatus.DISMISSED
        flag.save()
        log_action(actor, "DUPLICATE_DISMISSED", target=new, summary=f"{new.reference} is not a duplicate of {old.reference}")
        return "Marked as not a duplicate."
    flag.status = DuplicateStatus.CONFIRMED
    flag.save()
    log_action(actor, "DUPLICATE_CONFIRMED", target=new, summary=f"{new.reference} confirmed as a duplicate of {old.reference}")
    if new.status in (S.NEEDS_VERIFICATION, S.DEPARTMENT_ASSIGNED, S.PENDING):
        from .workflow import reject_complaint
        reject_complaint(new, actor=actor, reason=f"This repeats an earlier complaint ({old.reference}) that is already being handled.")
        return f"Confirmed. {new.reference} was closed as a duplicate and the citizen was told."
    return "Confirmed as a duplicate. The complaint has already been worked on, so it was left open."
