"""
Routing service. The BACKEND decides the department; the browser has no say.

    saved complaint (SUBMITTED)
      -> predict department from title + description        (ml_engine.predict)
      -> rule-based priority and SLA deadline                (independent of the model)
      -> confidence >= model threshold AND department active?
           yes -> DEPARTMENT_ASSIGNED -> PENDING             (appears in that department's queue)
           no  -> NEEDS_VERIFICATION                         (an administrator decides)
      -> if the model is missing or errors: NEEDS_VERIFICATION (the complaint is never lost)
"""
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from departments.models import Department
from departments.services import sla_hours_for
from ml_engine.exceptions import ModelUnavailableError
from ml_engine.predict import predict

from ..models import Complaint, ComplaintStatus as S, RoutingMethod
from . import alerts
from .priority import decide_priority
from .transitions import transition_complaint

logger = logging.getLogger("routelync")

REASON_TEXT = {
    "low_confidence": "AI confidence is below the threshold; an administrator must choose the department",
    "no_usable_text": "The text had no usable words for the AI; an administrator must choose the department",
    "no_known_terms": "The AI did not recognise any of the words; an administrator must choose the department",
    "model_unavailable": "The AI model was unavailable; an administrator must choose the department",
    "error": "The AI failed on this complaint; an administrator must choose the department",
    "department_unavailable": "The predicted department is not active; an administrator must choose the department",
}


class RoutingError(Exception):
    pass


@dataclass(frozen=True)
class RoutingOutcome:
    status: str
    department: Department | None
    reason: str
    auto_routed: bool


def route_complaint(complaint: Complaint) -> RoutingOutcome:
    if complaint.status != S.SUBMITTED:
        raise RoutingError(f"{complaint.reference} has already been processed (status {complaint.status}).")

    text = f"{complaint.title}. {complaint.description}"
    prediction, reason = None, ""
    try:
        prediction = predict(text)
        reason = prediction.reason
    except ModelUnavailableError as exc:
        reason = "model_unavailable"
        logger.error("Routing %s without AI: %s", complaint.reference, exc)
    except Exception:  # noqa: BLE001 - any model failure must degrade to manual verification
        reason = "error"
        logger.exception("Prediction failed for %s", complaint.reference)

    decision = decide_priority(text)
    deadline = complaint.created_at + timedelta(hours=sla_hours_for(decision.priority))
    now = timezone.now()

    fields = {"priority": decision.priority, "priority_reason": decision.reason,
              "sla_deadline": deadline, "routing_reason": reason}
    department = None
    if prediction is not None:
        fields.update(
            cleaned_text=prediction.cleaned_text,
            ai_confidence=prediction.confidence if prediction.department_code else None,   # None = no prediction made
            ai_probabilities=prediction.probabilities, ai_terms=prediction.top_terms,
            ai_model_id=prediction.model_id, ai_predicted_at=now,
            predicted_department=(Department.objects.filter(code=prediction.department_code).first()
                                  if prediction.department_code else None))
        if not prediction.needs_verification:
            department = Department.objects.filter(code=prediction.department_code, is_active=True).first()
            if department is None:
                fields["routing_reason"] = reason = "department_unavailable"

    with transaction.atomic():
        transition_complaint(complaint, S.AI_PROCESSING, note="AI analysis started")
        if department is not None:
            fields.update(department=department, routing_method=RoutingMethod.AUTO, routed_at=now, routing_reason="")
            transition_complaint(
                complaint, S.DEPARTMENT_ASSIGNED, updates=fields,
                note=f"AI routed to {department.name} (confidence {prediction.confidence:.0%}, model v{prediction.model_version})")
            transition_complaint(complaint, S.PENDING, note=f"Added to the {department.name} department queue")
            alerts.to_citizen(complaint, "ROUTED", f"Your complaint {complaint.reference} was sent to the {department.name} department.")
            alerts.to_department_officers(complaint, "NEW_COMPLAINT",
                                          f"New complaint {complaint.reference}: {complaint.title[:70]} ({complaint.get_priority_display()} priority)")
        else:
            transition_complaint(complaint, S.NEEDS_VERIFICATION, updates=fields,
                                 note=REASON_TEXT.get(reason, "Needs verification"))
            alerts.to_citizen(complaint, "UNDER_REVIEW", f"Your complaint {complaint.reference} is being reviewed before it is sent to a department.")
            alerts.to_administrators(complaint, "NEEDS_ROUTING", f"{complaint.reference} needs a department to be chosen: {complaint.title[:70]}")
    from .duplicates import flag_possible_duplicates
    flag_possible_duplicates(complaint)
    logger.info("Routed %s: %s (%s)", complaint.reference, complaint.status, reason or "auto")
    return RoutingOutcome(complaint.status, department, reason, auto_routed=department is not None)


@transaction.atomic
def manual_route(complaint: Complaint, department: Department, *, actor, note="") -> Complaint:
    """Administrator chooses the department for a complaint waiting in NEEDS_VERIFICATION.
    (Phase 10 puts a screen on this and adds the correction record and audit entry.)"""
    if not department.is_active:
        raise RoutingError("Cannot route to an inactive department.")
    now = timezone.now()
    transition_complaint(
        complaint, S.DEPARTMENT_ASSIGNED, actor=actor,
        updates={"department": department, "routing_method": RoutingMethod.MANUAL, "routed_at": now},
        note=(note or f"Administrator routed to {department.name}"))
    transition_complaint(complaint, S.PENDING, actor=actor, note=f"Added to the {department.name} department queue")
    alerts.to_citizen(complaint, "ROUTED", f"Your complaint {complaint.reference} was sent to the {department.name} department.")
    alerts.to_department_officers(complaint, "NEW_COMPLAINT",
                                  f"New complaint {complaint.reference}: {complaint.title[:70]} ({complaint.get_priority_display()} priority)")
    return complaint
