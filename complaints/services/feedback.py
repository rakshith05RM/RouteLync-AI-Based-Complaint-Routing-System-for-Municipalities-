from django.db import IntegrityError, transaction

from ..models import Complaint, ComplaintStatus as S, Feedback
from .errors import WorkflowError


@transaction.atomic
def submit_feedback(complaint, *, citizen, rating, comment="") -> Feedback:
    locked = Complaint.objects.select_for_update().get(pk=complaint.pk)
    if locked.citizen_id != citizen.pk:
        raise WorkflowError("You can only rate your own complaints.")
    if locked.status not in (S.RESOLVED, S.CLOSED):
        raise WorkflowError("Feedback can be given once the complaint has been resolved.")
    if not 1 <= int(rating) <= 5:
        raise WorkflowError("Choose a rating from 1 to 5.")
    if Feedback.objects.filter(complaint=locked).exists():
        raise WorkflowError("You have already given feedback for this complaint.")
    try:
        feedback = Feedback.objects.create(complaint=locked, rating=int(rating), comment=comment[:500])
    except IntegrityError:                         # two simultaneous submissions: the unique key wins
        raise WorkflowError("You have already given feedback for this complaint.")
    if feedback.rating <= 2:
        from . import alerts
        alerts.to_department_officers(locked, "LOW_RATING", f"{locked.reference} received a low rating ({feedback.rating}/5) from the citizen.")
    return feedback
