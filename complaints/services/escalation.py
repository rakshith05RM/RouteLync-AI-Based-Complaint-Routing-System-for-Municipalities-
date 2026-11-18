"""
SLA warnings and escalation.

    approaching deadline  -> warning to the department's officers (once)
    deadline passed       -> level 1: Department Head (and the officers are told)
    still open N hours later -> level 2: Administrators
    unrouted and overdue  -> level 2 directly (no department head exists yet)

Escalation never changes the lifecycle status; it adds an EscalationEvent and raises
Complaint.escalation_level, so the work itself can carry on. `run_sla_check` is safe to run
repeatedly (every few minutes from cron / Task Scheduler): every step re-checks the rules under a lock.
"""
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from departments.models import OfficerProfile

from ..models import ACTIVE_STATUSES, Complaint, ComplaintStatus as S, EscalationEvent, EscalationLevel
from ..sla import sla_state
from . import alerts
from .errors import WorkflowError
from .transitions import log_event

logger = logging.getLogger("routelync")


@dataclass
class SlaCheckResult:
    warned: int = 0
    level1: int = 0
    level2: int = 0
    unrouted: int = 0

    def summary(self) -> str:
        return (f"warnings sent: {self.warned}, escalated to department head: {self.level1}, "
                f"escalated to administrators: {self.level2 + self.unrouted}")


def _head_for(department):
    profile = OfficerProfile.objects.filter(department=department, is_department_head=True, user__is_active=True).select_related("user").first()
    return profile.user if profile else None


def _record(locked, level, *, reason, actor=None, automatic=False):
    head = _head_for(locked.department) if level == EscalationLevel.DEPARTMENT_HEAD and locked.department_id else None
    EscalationEvent.objects.create(complaint=locked, level=level, reason=reason[:255], escalated_to=head,
                                   triggered_by=actor, automatic=automatic)
    locked.escalation_level = level
    locked.save(update_fields=["escalation_level", "updated_at"])
    label = EscalationLevel(level).label
    log_event(locked, f"Escalated to {label}: {reason}", actor=actor)
    return head


def _tell(locked, level, reason, head):
    text = f"Escalated: {locked.reference} ({locked.title[:60]}) - {reason}"
    if level == EscalationLevel.DEPARTMENT_HEAD:
        if head:
            alerts.notify(head, text, link=alerts._officer_link(locked), kind="ESCALATED", complaint_id=locked.pk)
        else:                                       # no head configured: do not let it vanish
            alerts.to_department_officers(locked, "ESCALATED", text)
        alerts.to_administrators(locked, "ESCALATED_INFO", text) if head is None else None
    else:
        alerts.to_administrators(locked, "ESCALATED", text)
        alerts.to_department_officers(locked, "ESCALATED", text, heads_only=True)


# --------------------------------------------------------------------------------------------- manual
@transaction.atomic
def escalate_complaint(complaint, *, actor, reason) -> Complaint:
    """An officer asks for help. Ordinary officers escalate to the Department Head; the head to Administrators."""
    locked = Complaint.objects.select_for_update().get(pk=complaint.pk)
    if locked.status not in ACTIVE_STATUSES:
        raise WorkflowError("Only complaints that are still being worked on can be escalated.")
    profile = OfficerProfile.objects.filter(user=actor).first()
    level = EscalationLevel.ADMINISTRATOR if profile and profile.is_department_head else EscalationLevel.DEPARTMENT_HEAD
    if locked.escalation_level >= level:
        raise WorkflowError(f"This complaint has already been escalated to the {EscalationLevel(locked.escalation_level).label}.")
    head = _record(locked, level, reason=f"Escalated by {actor.full_name}: {reason}", actor=actor)
    _tell(locked, level, reason, head)
    complaint.refresh_from_db()
    return complaint


# ------------------------------------------------------------------------------------------ automatic
def _warn(complaint_id, now) -> bool:
    with transaction.atomic():
        c = Complaint.objects.select_for_update().get(pk=complaint_id)
        if c.status not in ACTIVE_STATUSES or c.sla_warned_at or c.escalation_level or not c.sla_deadline or c.sla_deadline <= now:
            return False
        window = (c.sla_deadline - c.created_at).total_seconds()
        if (c.sla_deadline - now).total_seconds() > window * settings.SLA_WARNING_FRACTION:
            return False
        c.sla_warned_at = now
        c.save(update_fields=["sla_warned_at", "updated_at"])
        alerts.to_department_officers(c, "SLA_WARNING", f"{c.reference} is approaching its deadline: {sla_state(c.sla_deadline, now).label}")
        return True


def _auto_level1(complaint_id, now) -> bool:
    with transaction.atomic():
        c = Complaint.objects.select_for_update().get(pk=complaint_id)
        if c.status not in ACTIVE_STATUSES or c.escalation_level >= 1 or not c.sla_deadline or c.sla_deadline >= now:
            return False
        reason = f"SLA deadline passed ({sla_state(c.sla_deadline, now).label.lower()})"
        head = _record(c, EscalationLevel.DEPARTMENT_HEAD, reason=reason, automatic=True)
        _tell(c, EscalationLevel.DEPARTMENT_HEAD, reason, head)
        return True


def _auto_level2(complaint_id, now) -> bool:
    with transaction.atomic():
        c = Complaint.objects.select_for_update().get(pk=complaint_id)
        if c.status not in ACTIVE_STATUSES or c.escalation_level != 1:
            return False
        first = c.escalations.filter(level=EscalationLevel.DEPARTMENT_HEAD).order_by("-created_at").first()
        if first is None or first.created_at > now - timedelta(hours=settings.ESCALATION_LEVEL2_AFTER_HOURS):
            return False
        reason = f"Still unresolved {settings.ESCALATION_LEVEL2_AFTER_HOURS} hours after escalation to the Department Head"
        _record(c, EscalationLevel.ADMINISTRATOR, reason=reason, automatic=True)
        _tell(c, EscalationLevel.ADMINISTRATOR, reason, None)
        return True


def _auto_unrouted(complaint_id, now) -> bool:
    with transaction.atomic():
        c = Complaint.objects.select_for_update().get(pk=complaint_id)
        if c.status != S.NEEDS_VERIFICATION or c.escalation_level or not c.sla_deadline or c.sla_deadline >= now:
            return False
        reason = "Still waiting for routing verification after its deadline"
        _record(c, EscalationLevel.ADMINISTRATOR, reason=reason, automatic=True)
        _tell(c, EscalationLevel.ADMINISTRATOR, reason, None)
        return True


def run_sla_check(now=None) -> SlaCheckResult:
    now = now or timezone.now()
    result = SlaCheckResult()
    base = Complaint.objects.filter(sla_deadline__isnull=False)
    # Decide who is eligible for level 2 BEFORE this run creates new level-1 escalations, so a complaint
    # can never jump from "not escalated" to "administrators" within a single run.
    level2_candidates = list(base.filter(status__in=ACTIVE_STATUSES, escalation_level=1).values_list("pk", flat=True))

    for pk in base.filter(status__in=ACTIVE_STATUSES, escalation_level=0, sla_warned_at__isnull=True,
                          sla_deadline__gt=now).values_list("pk", flat=True):
        result.warned += _warn(pk, now)
    for pk in base.filter(status__in=ACTIVE_STATUSES, escalation_level=0, sla_deadline__lt=now).values_list("pk", flat=True):
        result.level1 += _auto_level1(pk, now)
    for pk in level2_candidates:
        result.level2 += _auto_level2(pk, now)
    for pk in base.filter(status=S.NEEDS_VERIFICATION, escalation_level=0, sla_deadline__lt=now).values_list("pk", flat=True):
        result.unrouted += _auto_unrouted(pk, now)
    if any((result.warned, result.level1, result.level2, result.unrouted)):
        logger.info("SLA check: %s", result.summary())
    return result
