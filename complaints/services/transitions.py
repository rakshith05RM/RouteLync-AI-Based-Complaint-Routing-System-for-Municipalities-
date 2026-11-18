"""
The ONLY place a complaint's status may change. Every change is validated against the allowed
transitions, written to the append-only history, and happens in one transaction with the row locked.
(Audit-log and notification hooks are added in Phases 9-10 here, so no caller can forget them.)
"""
from django.db import transaction

from ..models import Complaint, ComplaintStatus as S, ComplaintStatusHistory
from audit.services import log_action

from .errors import WorkflowError

ALLOWED_TRANSITIONS = {
    S.SUBMITTED: {S.AI_PROCESSING, S.REJECTED},
    S.AI_PROCESSING: {S.DEPARTMENT_ASSIGNED, S.NEEDS_VERIFICATION},
    S.NEEDS_VERIFICATION: {S.DEPARTMENT_ASSIGNED, S.REJECTED},
    S.DEPARTMENT_ASSIGNED: {S.PENDING, S.REJECTED},
    S.PENDING: {S.ASSIGNED_TO_WORKER, S.REJECTED},
    S.ASSIGNED_TO_WORKER: {S.IN_PROGRESS, S.PENDING},
    S.IN_PROGRESS: {S.RESOLVED, S.ASSIGNED_TO_WORKER},   # back to ASSIGNED = reassigned to another worker
    S.RESOLVED: {S.CLOSED, S.REOPENED},
    S.REOPENED: {S.PENDING, S.ASSIGNED_TO_WORKER},
    S.CLOSED: set(),       # terminal
    S.REJECTED: set(),     # terminal
}


class InvalidTransition(WorkflowError):
    pass


@transaction.atomic
def transition_complaint(complaint: Complaint, to_status, *, actor=None, note="", updates=None) -> Complaint:
    """Move `complaint` to `to_status`, optionally setting other fields in the same save."""
    locked = Complaint.objects.select_for_update().get(pk=complaint.pk)   # fresh status, row locked
    if to_status not in ALLOWED_TRANSITIONS.get(locked.status, set()):
        raise InvalidTransition(f"That action is not available while the complaint is '{locked.get_status_display()}'.")

    if to_status == S.RESOLVED and not (updates or {}).get("resolution_photo", locked.resolution_photo):
        raise WorkflowError("A photo of the completed work is required before a complaint can be marked as resolved.")

    from_status = locked.status
    locked.status = to_status
    for field, value in (updates or {}).items():
        setattr(locked, field, value)
    locked.save()
    ComplaintStatusHistory.objects.create(
        complaint=locked, from_status=from_status, to_status=to_status, changed_by=actor, note=note[:255])
    if actor is not None:                                  # system steps (AI routing) are in the complaint history already
        log_action(actor, "COMPLAINT_STATUS", target=locked, summary=f"{locked.reference}: {from_status} -> {to_status}",
                   details={"note": note[:255]})

    for field in locked._meta.concrete_fields:           # keep the caller's object in sync
        setattr(complaint, field.attname, getattr(locked, field.attname))
    return complaint


def log_event(complaint: Complaint, note: str, *, actor=None) -> None:
    """Record something that happened without changing the status (a reassignment, a send-back...)."""
    ComplaintStatusHistory.objects.create(
        complaint=complaint, from_status=complaint.status, to_status=complaint.status, changed_by=actor, note=note[:255])
    if actor is not None:
        log_action(actor, "COMPLAINT_EVENT", target=complaint, summary=f"{complaint.reference}: {note}"[:255])
