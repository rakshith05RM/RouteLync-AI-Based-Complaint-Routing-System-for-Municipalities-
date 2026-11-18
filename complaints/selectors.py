"""
Read-side access rules. NEVER call Complaint.objects.all() in a view: always start from
complaints_visible_to(request.user), so authorisation lives in one place.
"""
from accounts.models import Role
from departments.services import department_for

from .models import Complaint


def complaints_visible_to(user):
    qs = Complaint.objects.all()
    if not user.is_authenticated or not user.is_active:
        return qs.none()
    if user.role == Role.CITIZEN:
        return qs.filter(citizen=user)
    if user.role == Role.ADMIN:
        return qs
    if user.role == Role.OFFICER:
        dept = department_for(user)
        # Guard matters: filter(department=None) would match every unrouted complaint.
        return qs.filter(department=dept) if dept is not None and dept.is_active else qs.none()
    if user.role == Role.FIELD_WORKER:
        # One filter() call: both conditions must hold for the SAME assignment row.
        return qs.filter(assignments__assigned_to=user, assignments__ended_at__isnull=True)
    return qs.none()


# ---------------------------------------------------------------------------- officer dashboard queries
from django.db.models import Count, Min, Q  # noqa: E402
from django.db.models.functions import Lower  # noqa: E402
from django.utils import timezone  # noqa: E402

from departments.models import Priority  # noqa: E402

from .models import ACTIVE_STATUSES, CLOSED_STATUSES, ComplaintStatus  # noqa: E402


def officer_summary(queryset, now=None) -> dict:
    """Headline numbers for the officer's department (not affected by the list filters)."""
    now = now or timezone.now()
    return queryset.aggregate(
        open=Count("id", filter=~Q(status__in=CLOSED_STATUSES)),
        pending=Count("id", filter=Q(status=ComplaintStatus.PENDING)),
        in_progress=Count("id", filter=Q(status__in=[ComplaintStatus.ASSIGNED_TO_WORKER, ComplaintStatus.IN_PROGRESS])),
        overdue=Count("id", filter=Q(status__in=ACTIVE_STATUSES, sla_deadline__lt=now)),
        urgent=Count("id", filter=Q(status__in=ACTIVE_STATUSES, priority__in=[Priority.CRITICAL, Priority.HIGH])),
        escalated=Count("id", filter=Q(status__in=ACTIVE_STATUSES, escalation_level__gt=0)),
        awaiting=Count("id", filter=Q(status=ComplaintStatus.IN_PROGRESS,
                                      resolutions__outcome="PENDING_VERIFICATION"), distinct=True),
    )


def location_breakdown(queryset, *, area=None, ward=None, now=None):
    """
    One level of the Department -> Area -> Ward -> Street drill-down: active complaints (and how
    many of them are overdue) grouped by the next level down.
    Returns (level, rows) where each row has key, label, active, overdue.
    """
    now = now or timezone.now()
    active = queryset.filter(status__in=ACTIVE_STATUSES)
    counts = dict(active=Count("id"), overdue=Count("id", filter=Q(sla_deadline__lt=now)))

    if area is None:
        rows = (active.values(key=_F("location__area_id"), label=_F("location__area__name"))
                .annotate(**counts).order_by("-active", "label"))
        return "area", list(rows)
    if ward is None:
        rows = (active.filter(location__area=area, location__ward__isnull=False)
                .values(key=_F("location__ward_id"), label=_F("location__ward__number"))
                .annotate(**counts).order_by("-active", "label"))
        return "ward", list(rows)
    # Streets are grouped case-insensitively so "4th Main Road" and "4TH main road" are one street.
    rows = (active.filter(location__ward=ward).annotate(street_key=Lower("location__street"))
            .values("street_key").annotate(label=Min("location__street"), **counts).order_by("-active", "label"))
    return "street", [{"key": r["street_key"], "label": r["label"], "active": r["active"], "overdue": r["overdue"]} for r in rows]


def _F(name):
    from django.db.models import F
    return F(name)
