from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class EscalationLevel(models.IntegerChoices):
    DEPARTMENT_HEAD = 1, "Department Head"
    ADMINISTRATOR = 2, "Administrator"


class EscalationEvent(models.Model):
    """
    A record that a complaint was escalated. Escalation never overwrites the complaint's lifecycle
    status, so the work (assignment, resolution, verification) can carry on while senior staff are told.
    """

    complaint = models.ForeignKey("complaints.Complaint", on_delete=models.CASCADE, related_name="escalations")
    level = models.PositiveSmallIntegerField(choices=EscalationLevel.choices)
    reason = models.CharField(max_length=255)
    escalated_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                     help_text="The Department Head for level 1; empty for level 2 (all administrators)")
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                     help_text="Empty when the system escalated automatically")
    automatic = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["complaint", "level"], name="esc_complaint_level_idx")]

    def __str__(self):
        return f"{self.complaint.reference} escalated to {self.get_level_display()}"


class Feedback(models.Model):
    """A citizen's rating after a complaint has been resolved. One per complaint."""

    complaint = models.OneToOneField("complaints.Complaint", on_delete=models.CASCADE, related_name="feedback")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="feedback_rating_1_to_5")]

    def __str__(self):
        return f"{self.complaint.reference}: {self.rating}/5"
