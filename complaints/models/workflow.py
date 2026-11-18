"""
Workflow tables (Phase 8): who is working on a complaint, what was said, and how it was resolved.

"One active assignment per complaint" is enforced in the DATABASE with a nullable unique column
(`active_key`): it holds the complaint id while the assignment is active and NULL afterwards, and
unique indexes allow many NULLs. (MySQL has no conditional unique index, so this is the portable way.)
"""
from django.conf import settings
from django.db import models


class ComplaintAssignment(models.Model):
    complaint = models.ForeignKey("complaints.Complaint", on_delete=models.CASCADE, related_name="assignments")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="complaint_assignments")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    active_key = models.PositiveBigIntegerField(null=True, unique=True, editable=False)

    class Meta:
        ordering = ["-assigned_at", "-id"]
        indexes = [models.Index(fields=["assigned_to", "ended_at"], name="asg_worker_active_idx")]

    def save(self, *args, **kwargs):
        self.active_key = self.complaint_id if self.ended_at is None else None
        super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    def __str__(self):
        return f"{self.complaint.reference} -> {self.assigned_to.full_name}"


class RemarkVisibility(models.TextChoices):
    PUBLIC = "PUBLIC", "Visible to the citizen"
    INTERNAL = "INTERNAL", "Staff only"


class ComplaintRemark(models.Model):
    complaint = models.ForeignKey("complaints.Complaint", on_delete=models.CASCADE, related_name="remarks")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    text = models.TextField(max_length=1000)
    visibility = models.CharField(max_length=10, choices=RemarkVisibility.choices, default=RemarkVisibility.INTERNAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.complaint.reference}: {self.text[:40]}"


class ResolutionOutcome(models.TextChoices):
    PENDING_VERIFICATION = "PENDING_VERIFICATION", "Awaiting officer verification"
    VERIFIED = "VERIFIED", "Verified by officer"
    SENT_BACK = "SENT_BACK", "Sent back by officer"
    DISPUTED = "DISPUTED", "Disputed by citizen"


class Resolution(models.Model):
    """One attempt by a field worker to finish the job. A complaint can have several (send-back, reopen)."""

    complaint = models.ForeignKey("complaints.Complaint", on_delete=models.CASCADE, related_name="resolutions")
    remarks = models.TextField(max_length=1000)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    resolved_at = models.DateTimeField(auto_now_add=True)
    outcome = models.CharField(max_length=25, choices=ResolutionOutcome.choices, default=ResolutionOutcome.PENDING_VERIFICATION)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True)
    citizen_confirmed_at = models.DateTimeField(null=True, blank=True)
    dispute_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-resolved_at", "-id"]
        indexes = [models.Index(fields=["complaint", "outcome"], name="res_complaint_outcome_idx")]

    def __str__(self):
        return f"{self.complaint.reference} resolution ({self.outcome})"
