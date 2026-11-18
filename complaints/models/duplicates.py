from django.conf import settings
from django.db import models
from django.db.models import F, Q


class DuplicateStatus(models.TextChoices):
    PENDING = "PENDING", "Waiting for a person to decide"
    CONFIRMED = "CONFIRMED", "Confirmed duplicate"
    DISMISSED = "DISMISSED", "Not a duplicate"


class DuplicateFlag(models.Model):
    """
    The system suspects `complaint` repeats the older `possible_duplicate_of`. It is only a suspicion:
    nothing is merged or removed until a person decides.
    """

    complaint = models.ForeignKey("complaints.Complaint", on_delete=models.CASCADE, related_name="duplicate_flags")
    possible_duplicate_of = models.ForeignKey("complaints.Complaint", on_delete=models.CASCADE, related_name="duplicate_reports")
    similarity = models.FloatField()
    reason = models.CharField(max_length=40, help_text="Why it was compared: same street, nearby GPS or same ward")
    status = models.CharField(max_length=10, choices=DuplicateStatus.choices, default=DuplicateStatus.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-similarity", "id"]
        constraints = [
            models.UniqueConstraint(fields=["complaint", "possible_duplicate_of"], name="uniq_duplicate_pair"),
            models.CheckConstraint(condition=~Q(complaint=F("possible_duplicate_of")), name="duplicate_not_itself"),
            models.CheckConstraint(condition=Q(similarity__gte=0, similarity__lte=1), name="duplicate_similarity_range"),
        ]

    def __str__(self):
        return f"{self.complaint.reference} may repeat {self.possible_duplicate_of.reference} ({self.similarity:.0%})"
