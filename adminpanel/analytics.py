"""Numbers for the administrator dashboard. Everything is computed from the database; nothing is estimated."""
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

from complaints.models import (ACTIVE_STATUSES, Complaint, ComplaintStatus as S, Feedback, RoutingCorrection,
                               RoutingMethod)
from departments.models import Priority
from ml_engine.models import MLModel, TrainingSample

from .charts import line_points


def summary_counts(now=None) -> dict:
    now = now or timezone.now()
    return Complaint.objects.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status__in=[S.DEPARTMENT_ASSIGNED, S.PENDING])),
        in_progress=Count("id", filter=Q(status__in=[S.ASSIGNED_TO_WORKER, S.IN_PROGRESS])),
        resolved=Count("id", filter=Q(status__in=[S.RESOLVED, S.CLOSED])),
        overdue=Count("id", filter=Q(status__in=ACTIVE_STATUSES, sla_deadline__lt=now)),
        escalated=Count("id", filter=Q(status__in=ACTIVE_STATUSES, escalation_level__gt=0)),
        needs_verification=Count("id", filter=Q(status=S.NEEDS_VERIFICATION)),
    )


def _bars(rows):
    top = max((v for _, v in rows), default=0)
    return [{"label": label, "value": value, "percent": round(100 * value / top) if top else 0} for label, value in rows]


def by_department():
    rows = (Complaint.objects.filter(department__isnull=False).values_list("department__name").annotate(n=Count("id")).order_by("-n"))
    return _bars([(name, n) for name, n in rows])


def by_area(limit=10):
    rows = (Complaint.objects.values_list("location__area__name").annotate(n=Count("id")).order_by("-n", "location__area__name")[:limit])
    return _bars([(name, n) for name, n in rows])


def by_ward(limit=10):
    rows = (Complaint.objects.filter(location__ward__isnull=False)
            .values_list("location__area__name", "location__ward__number").annotate(n=Count("id"))
            .order_by("-n", "location__ward__number")[:limit])
    return _bars([(f"{area}, Ward {number}", n) for area, number, n in rows])


def status_distribution():
    counts = dict(Complaint.objects.values_list("status").annotate(n=Count("id")))
    labels = dict(S.choices)
    return _bars([(labels[s], counts[s]) for s, _ in S.choices if counts.get(s)])


def priority_distribution():
    counts = dict(Complaint.objects.values_list("priority").annotate(n=Count("id")))
    return _bars([(label, counts.get(value, 0)) for value, label in reversed(Priority.choices)])


def over_time(days=30, now=None):
    """Complaints submitted per local day. Bucketed in Python, which avoids database time-zone functions."""
    now = timezone.localtime(now or timezone.now())
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    counts = Counter(timezone.localtime(t).date() for t in Complaint.objects.filter(created_at__gte=start).values_list("created_at", flat=True))
    series = [((start + timedelta(days=i)).date(), 0) for i in range(days)]
    series = [(day, counts.get(day, 0)) for day, _ in series]
    return {"series": series, "total": sum(v for _, v in series), "points": line_points([v for _, v in series]),
            "peak": max(series, key=lambda dv: dv[1]) if series else None}


def resolution_time_by_department():
    """Average hours from submission to verified resolution, per department (resolved complaints only)."""
    sums, counts = defaultdict(float), Counter()
    rows = Complaint.objects.filter(resolved_at__isnull=False, department__isnull=False).values_list("department__name", "created_at", "resolved_at")
    for name, created, resolved in rows:
        sums[name] += (resolved - created).total_seconds() / 3600
        counts[name] += 1
    return _bars(sorted(((name, round(sums[name] / counts[name], 1)) for name in sums), key=lambda x: -x[1]))


def feedback_summary():
    agg = Feedback.objects.aggregate(avg=Avg("rating"), n=Count("id"))
    dist = dict(Feedback.objects.values_list("rating").annotate(n=Count("id")))
    by_dept = (Feedback.objects.filter(complaint__department__isnull=False).values_list("complaint__department__name")
               .annotate(avg=Avg("rating"), n=Count("id")).order_by("-avg"))
    return {"average": round(agg["avg"], 2) if agg["avg"] is not None else None, "count": agg["n"],
            "distribution": _bars([(f"{r} star{'s' if r > 1 else ''}", dist.get(r, 0)) for r in (5, 4, 3, 2, 1)]),
            "by_department": [{"name": name, "average": round(avg, 2), "count": n} for name, avg, n in by_dept],
            "low": list(Feedback.objects.filter(rating__lte=2).select_related("complaint").order_by("-created_at")[:5])}


def ai_overview():
    model = MLModel.objects.filter(is_active=True).first()
    auto = Complaint.objects.filter(routing_method=RoutingMethod.AUTO).count()
    corrected = RoutingCorrection.objects.filter(ai_was_correct=False, was_unrouted=False).count()
    queue = RoutingCorrection.objects.filter(was_unrouted=True)
    return {
        "model": model,
        "samples": TrainingSample.objects.filter(is_verified=True).count(),
        "auto_routed": auto, "corrected_after_routing": corrected,
        "correction_rate": round(100 * corrected / auto, 1) if auto else None,
        "queue_decided": queue.count(), "queue_agreed_with_ai": queue.filter(ai_was_correct=True).count(),
        "added_to_training": RoutingCorrection.objects.filter(training_sample__isnull=False).count(),
    }
