"""
Human-in-the-loop routing. An administrator either answers a complaint waiting in the verification queue
or moves an AI-routed complaint to the correct department. Each decision is stored as a RoutingCorrection
and, if the administrator agrees, becomes a verified training example for a future model.
"""
from django.db import transaction
from django.utils import timezone

from audit.services import log_action
from departments.models import Department
from ml_engine.dataset import add_verified_sample

from ..models import Complaint, ComplaintStatus as S, RoutingCorrection, RoutingMethod
from . import alerts
from .errors import WorkflowError
from .routing import manual_route
from .transitions import log_event, transition_complaint
from .workflow import end_assignments

REROUTABLE = (S.DEPARTMENT_ASSIGNED, S.PENDING, S.ASSIGNED_TO_WORKER)


@transaction.atomic
def route_by_admin(complaint, department: Department, *, actor, note="", add_to_training=False):
    """Returns (RoutingCorrection, training_note). training_note explains why a sample was not added."""
    locked = Complaint.objects.select_for_update().get(pk=complaint.pk)
    if not department.is_active:
        raise WorkflowError("That department is not active.")
    predicted = locked.predicted_department
    was_unrouted = locked.status == S.NEEDS_VERIFICATION

    if was_unrouted:
        manual_route(complaint, department, actor=actor, note=note)
    elif locked.status in REROUTABLE:
        if locked.department_id == department.pk:
            raise WorkflowError("The complaint is already in that department.")
        old = locked.department
        end_assignments(locked)
        updates = {"department": department, "routing_method": RoutingMethod.MANUAL, "routed_at": timezone.now()}
        text = note or f"Administrator moved the complaint from {old.name} to {department.name}"
        if locked.status == S.ASSIGNED_TO_WORKER:
            transition_complaint(complaint, S.PENDING, actor=actor, note=text, updates=updates)
        else:
            for field, value in updates.items():
                setattr(locked, field, value)
            locked.save(update_fields=list(updates) + ["updated_at"])
            log_event(locked, text, actor=actor)
            complaint.refresh_from_db()
        alerts.to_department_officers(complaint, "NEW_COMPLAINT", f"Moved to your department: {complaint.reference} - {complaint.title[:70]}")
        alerts.to_citizen(complaint, "ROUTED", f"Your complaint {complaint.reference} was sent to the {department.name} department.")
    else:
        raise WorkflowError("This complaint cannot be moved in its current state. Work has started or the complaint is finished.")

    sample, training_note = None, ""
    if add_to_training:
        sample, reason = add_verified_sample(text=f"{locked.title}. {locked.description}", department=department, complaint=locked)
        training_note = "" if sample else f"Not added to the training data: {reason}."
    correction = RoutingCorrection.objects.create(
        complaint=locked, predicted_department=predicted, corrected_department=department, corrected_by=actor,
        ai_was_correct=(predicted is not None and predicted.pk == department.pk), was_unrouted=was_unrouted,
        note=note[:255], training_sample=sample)
    log_action(actor, "ROUTING_VERIFIED" if was_unrouted else "ROUTING_CORRECTED", target=locked,
               summary=f"{locked.reference}: {predicted.name if predicted else 'no prediction'} -> {department.name}",
               details={"ai_was_correct": correction.ai_was_correct, "added_to_training": bool(sample)})
    return correction, training_note
