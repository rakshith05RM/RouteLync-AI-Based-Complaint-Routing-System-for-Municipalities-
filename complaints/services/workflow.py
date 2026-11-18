"""
Everyday workflow actions. Each function validates the business rules, locks the complaint row, changes
data and writes history in ONE transaction. Rule violations raise WorkflowError with a message that is
safe to show to the user. (Notification and audit-log hooks are added to these functions in Phases 9-10.)

    officer:        assign_worker / unassign_worker / change_priority / reject_complaint /
                    review_resolution / add_remark
    field worker:   start_work / complete_work / add_remark
    citizen:        confirm_resolution / reopen_complaint
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import Role
from departments.models import FieldWorkerProfile, Priority
from departments.services import sla_hours_for

from ..models import (Complaint, ComplaintAssignment, ComplaintImage, ComplaintRemark, ComplaintStatus as S,
                      ImageKind, RemarkVisibility, Resolution, ResolutionOutcome)
from . import alerts
from .errors import WorkflowError
from .submission import sanitize_image
from .transitions import log_event, transition_complaint

logger = logging.getLogger("routelync")

ASSIGNABLE = (S.PENDING, S.REOPENED, S.ASSIGNED_TO_WORKER, S.IN_PROGRESS)


def _lock(complaint) -> Complaint:
    return Complaint.objects.select_for_update().get(pk=complaint.pk)


def _active_assignment(complaint):
    return ComplaintAssignment.objects.filter(complaint=complaint, ended_at__isnull=True).select_related("assigned_to").first()


def _pending_resolution(complaint):
    return Resolution.objects.filter(complaint=complaint, outcome=ResolutionOutcome.PENDING_VERIFICATION).first()


def end_assignments(complaint, when=None):
    ComplaintAssignment.objects.filter(complaint=complaint, ended_at__isnull=True).update(
        ended_at=when or timezone.now(), active_key=None)


# ------------------------------------------------------------------------------------------ officer
@transaction.atomic
def assign_worker(complaint, worker, *, actor, note="") -> Complaint:
    locked = _lock(complaint)
    if locked.status not in ASSIGNABLE:
        raise WorkflowError(f"A complaint that is '{locked.get_status_display()}' cannot be assigned to a field worker.")
    profile = FieldWorkerProfile.objects.filter(user=worker).first()
    if worker.role != Role.FIELD_WORKER or profile is None:
        raise WorkflowError("The selected person is not a field worker.")
    if profile.department_id != locked.department_id:
        raise WorkflowError("That field worker belongs to a different department.")
    if not (profile.is_available and worker.is_active):
        raise WorkflowError(f"{worker.full_name} is not available for new work.")
    if _pending_resolution(locked):
        raise WorkflowError("Review the submitted resolution before reassigning this complaint.")

    previous = _active_assignment(locked)
    if previous and previous.assigned_to_id == worker.pk:
        raise WorkflowError(f"This complaint is already assigned to {worker.full_name}.")

    end_assignments(locked)
    ComplaintAssignment.objects.create(complaint=locked, assigned_to=worker, assigned_by=actor, note=note[:255])
    if previous:
        text = f"Reassigned from {previous.assigned_to.full_name} to {worker.full_name}"
    else:
        text = f"Assigned to field worker {worker.full_name}"
    if locked.status == S.ASSIGNED_TO_WORKER:
        log_event(locked, text, actor=actor)
    else:
        transition_complaint(complaint, S.ASSIGNED_TO_WORKER, actor=actor, note=text)
    complaint.refresh_from_db()
    alerts.to_worker(complaint, worker, "JOB_ASSIGNED", f"New job assigned to you: {complaint.reference} ({complaint.title[:60]})")
    alerts.to_citizen(complaint, "WORKER_ASSIGNED", f"A field worker has been assigned to your complaint {complaint.reference}.")
    return complaint


@transaction.atomic
def unassign_worker(complaint, *, actor) -> Complaint:
    locked = _lock(complaint)
    if locked.status != S.ASSIGNED_TO_WORKER:
        raise WorkflowError("Only a complaint that has not been started can be returned to the queue.")
    previous = _active_assignment(locked)
    end_assignments(locked)
    transition_complaint(complaint, S.PENDING, actor=actor,
                         note=f"Returned to the queue (was assigned to {previous.assigned_to.full_name})" if previous else "Returned to the queue")
    return complaint


@transaction.atomic
def change_priority(complaint, priority, *, actor, reason) -> Complaint:
    locked = _lock(complaint)
    if priority not in Priority.values:
        raise WorkflowError("Choose a valid priority.")
    if locked.status not in (S.PENDING, S.ASSIGNED_TO_WORKER, S.IN_PROGRESS, S.REOPENED, S.DEPARTMENT_ASSIGNED):
        raise WorkflowError("The priority of a finished complaint cannot be changed.")
    if priority == locked.priority:
        raise WorkflowError("The complaint already has that priority.")
    old = locked.get_priority_display()
    locked.priority = priority
    locked.priority_reason = f"Changed by {actor.full_name}: {reason}"[:120]
    locked.sla_deadline = locked.created_at + timedelta(hours=sla_hours_for(priority))   # clock still runs from submission
    locked.sla_warned_at = None                                                          # new deadline, new warning
    locked.save(update_fields=["priority", "priority_reason", "sla_deadline", "sla_warned_at", "updated_at"])
    log_event(locked, f"Priority changed from {old} to {locked.get_priority_display()}: {reason}", actor=actor)
    complaint.refresh_from_db()
    return complaint


@transaction.atomic
def reject_complaint(complaint, *, actor, reason) -> Complaint:
    locked = _lock(complaint)
    if locked.status not in (S.NEEDS_VERIFICATION, S.DEPARTMENT_ASSIGNED, S.PENDING):
        raise WorkflowError("A complaint can only be rejected before work has been assigned.")
    end_assignments(locked)
    transition_complaint(complaint, S.REJECTED, actor=actor, note=f"Rejected: {reason}",
                         updates={"closed_at": timezone.now()})
    ComplaintRemark.objects.create(complaint=locked, author=actor, text=f"Complaint rejected: {reason}",
                                   visibility=RemarkVisibility.PUBLIC)
    alerts.to_citizen(complaint, "REJECTED", f"Your complaint {complaint.reference} could not be taken forward: {reason}"[:255])
    return complaint


@transaction.atomic
def review_resolution(complaint, *, actor, approve: bool, note="") -> Complaint:
    locked = _lock(complaint)
    resolution = _pending_resolution(locked)
    if locked.status != S.IN_PROGRESS or resolution is None:
        raise WorkflowError("There is no submitted resolution waiting for review.")
    now = timezone.now()
    resolution.reviewed_by, resolution.reviewed_at, resolution.review_note = actor, now, note[:255]
    if approve:
        if not locked.resolution_photo:
            raise WorkflowError("The completed work has no photo, so the complaint cannot be marked as resolved.")
        resolution.outcome = ResolutionOutcome.VERIFIED
        resolution.save()
        transition_complaint(complaint, S.RESOLVED, actor=actor, note="Resolution verified by the officer",
                             updates={"resolved_at": now})
        alerts.to_citizen(complaint, "RESOLVED", f"Your complaint {complaint.reference} has been resolved. Please confirm that the problem is fixed.")
    else:
        if not note.strip():
            raise WorkflowError("Explain what still needs to be done when sending the work back.")
        resolution.outcome = ResolutionOutcome.SENT_BACK
        resolution.save()
        log_event(locked, f"Resolution sent back to the field worker: {note}", actor=actor)
        complaint.refresh_from_db()
        assignment = _active_assignment(locked)
        if assignment:
            alerts.to_worker(complaint, assignment.assigned_to, "SENT_BACK", f"{complaint.reference} was sent back: {note}"[:255])
    return complaint


# ------------------------------------------------------------------------------------ field worker
def _require_assignment(complaint, worker):
    assignment = _active_assignment(complaint)
    if assignment is None or assignment.assigned_to_id != worker.pk:
        raise WorkflowError("This complaint is not assigned to you.")
    return assignment


@transaction.atomic
def start_work(complaint, *, actor) -> Complaint:
    locked = _lock(complaint)
    _require_assignment(locked, actor)
    transition_complaint(complaint, S.IN_PROGRESS, actor=actor, note="Work started")
    alerts.to_citizen(complaint, "IN_PROGRESS", f"Work has started on your complaint {complaint.reference}.")
    return complaint


@transaction.atomic
def complete_work(complaint, *, actor, remarks, photo=None) -> Complaint:
    locked = _lock(complaint)
    _require_assignment(locked, actor)
    if locked.status != S.IN_PROGRESS:
        raise WorkflowError("Start the work before marking it as completed.")
    if _pending_resolution(locked):
        raise WorkflowError("Your completed work is already waiting for the officer's review.")
    if photo is None:
        raise WorkflowError("Please attach a photo of the finished work. A complaint cannot be resolved without one.")
    resolution = Resolution.objects.create(complaint=locked, remarks=remarks, resolved_by=actor)
    log_event(locked, "Work completed; waiting for the officer to verify", actor=actor)
    # The file is written last, after the database rows. The attempt keeps its own image record (history) and the
    # complaint points at the current proof of the fix through resolution_photo (one file, two references).
    image = ComplaintImage.objects.create(complaint=locked, image=sanitize_image(photo), kind=ImageKind.RESOLUTION,
                                          uploaded_by=actor, resolution=resolution)
    locked.resolution_photo = image.image.name
    locked.save(update_fields=["resolution_photo", "updated_at"])
    complaint.refresh_from_db()
    alerts.to_department_officers(complaint, "AWAITING_VERIFICATION",
                                  f"{complaint.reference}: work completed by {actor.full_name}, waiting for your verification.")
    alerts.to_citizen(complaint, "WORK_COMPLETED",
                      f"Work on your complaint {complaint.reference} has been completed and is waiting for department verification.")
    return complaint


# ----------------------------------------------------------------------------------------- citizen
@transaction.atomic
def confirm_resolution(complaint, *, citizen) -> Complaint:
    locked = _lock(complaint)
    if locked.citizen_id != citizen.pk:
        raise WorkflowError("You can only confirm your own complaints.")
    if locked.status != S.RESOLVED:
        raise WorkflowError("This complaint is not waiting for your confirmation.")
    now = timezone.now()
    Resolution.objects.filter(complaint=locked, outcome=ResolutionOutcome.VERIFIED, citizen_confirmed_at__isnull=True
                              ).update(citizen_confirmed_at=now)
    end_assignments(locked, now)
    transition_complaint(complaint, S.CLOSED, actor=citizen, note="Citizen confirmed the problem is fixed",
                         updates={"closed_at": now})
    return complaint


@transaction.atomic
def reopen_complaint(complaint, *, citizen, reason) -> Complaint:
    locked = _lock(complaint)
    if locked.citizen_id != citizen.pk:
        raise WorkflowError("You can only reopen your own complaints.")
    if locked.status != S.RESOLVED:
        raise WorkflowError("Only a resolved complaint can be reopened.")
    now = timezone.now()
    if locked.resolved_at and now - locked.resolved_at > timedelta(days=settings.REOPEN_WINDOW_DAYS):
        raise WorkflowError(f"A complaint can only be reopened within {settings.REOPEN_WINDOW_DAYS} days of being resolved. "
                            "Please submit a new complaint.")
    Resolution.objects.filter(complaint=locked, outcome=ResolutionOutcome.VERIFIED).update(
        outcome=ResolutionOutcome.DISPUTED, dispute_reason=reason[:500])
    end_assignments(locked, now)
    transition_complaint(complaint, S.REOPENED, actor=citizen, note="Citizen reported the problem is not fixed",
                         updates={"resolved_at": None, "sla_deadline": now + timedelta(hours=sla_hours_for(locked.priority)),
                                  "sla_warned_at": None, "escalation_level": 0,        # a reopened complaint gets a fresh clock
                                  "resolution_photo": ""})                              # ...and needs a new proof photo next time
    ComplaintRemark.objects.create(complaint=locked, author=citizen, text=f"Reopened by the citizen: {reason}",
                                   visibility=RemarkVisibility.PUBLIC)
    alerts.to_department_officers(complaint, "REOPENED", f"{complaint.reference} was reopened by the citizen: {reason}"[:255])
    return complaint


# ------------------------------------------------------------------------------------------ shared
@transaction.atomic
def add_remark(complaint, *, author, text, visibility=RemarkVisibility.INTERNAL) -> ComplaintRemark:
    if visibility not in RemarkVisibility.values:
        raise WorkflowError("Choose who can see this remark.")
    remark = ComplaintRemark.objects.create(complaint=complaint, author=author, text=text, visibility=visibility)
    if visibility == RemarkVisibility.PUBLIC and author.pk != complaint.citizen_id:
        alerts.to_citizen(complaint, "UPDATE", f"There is a new update on your complaint {complaint.reference}.")
    return remark
