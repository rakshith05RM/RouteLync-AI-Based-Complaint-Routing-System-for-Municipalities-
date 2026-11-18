"""
Core complaint tables (Phase 4). Later phases add columns/tables for AI prediction (Phase 5-6),
assignment, remarks, resolution, feedback (Phase 8-9) through new migrations.

Normalisation: the complaint, its location and its images are separate tables so each can change
independently. The selected area is stored directly because a ward is optional; when a ward is
provided, its area must match.
"""
import os
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from departments.models import Priority


class ComplaintStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    AI_PROCESSING = "AI_PROCESSING", "AI processing"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION", "Needs verification"
    DEPARTMENT_ASSIGNED = "DEPARTMENT_ASSIGNED", "Department assigned"
    PENDING = "PENDING", "Pending"
    ASSIGNED_TO_WORKER = "ASSIGNED_TO_WORKER", "Assigned to field worker"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"
    REJECTED = "REJECTED", "Rejected"
    REOPENED = "REOPENED", "Reopened"


# Statuses in which a department still owes work on the complaint (the SLA clock matters here).
ACTIVE_STATUSES = (ComplaintStatus.DEPARTMENT_ASSIGNED, ComplaintStatus.PENDING, ComplaintStatus.ASSIGNED_TO_WORKER,
                   ComplaintStatus.IN_PROGRESS, ComplaintStatus.REOPENED)
CLOSED_STATUSES = (ComplaintStatus.CLOSED, ComplaintStatus.REJECTED)
# Lifecycle order, used when sorting a list by status.
STATUS_ORDER = [ComplaintStatus.SUBMITTED, ComplaintStatus.AI_PROCESSING, ComplaintStatus.NEEDS_VERIFICATION,
                ComplaintStatus.DEPARTMENT_ASSIGNED, ComplaintStatus.PENDING, ComplaintStatus.ASSIGNED_TO_WORKER,
                ComplaintStatus.IN_PROGRESS, ComplaintStatus.REOPENED,
                ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED, ComplaintStatus.REJECTED]


class RoutingMethod(models.TextChoices):
    AUTO = "AUTO", "Automatic (AI)"
    MANUAL = "MANUAL", "Manual (administrator)"


# Citizens see simplified wording; internal states (e.g. "needs verification") stay internal.
CITIZEN_STATUS_LABELS = {
    ComplaintStatus.SUBMITTED: "Received",
    ComplaintStatus.AI_PROCESSING: "Received",
    ComplaintStatus.NEEDS_VERIFICATION: "Under review",
    ComplaintStatus.DEPARTMENT_ASSIGNED: "Sent to department",
    ComplaintStatus.PENDING: "Sent to department",
    ComplaintStatus.ASSIGNED_TO_WORKER: "Worker assigned",
    ComplaintStatus.IN_PROGRESS: "In progress",
    ComplaintStatus.RESOLVED: "Resolved - please confirm",
    ComplaintStatus.CLOSED: "Closed",
    ComplaintStatus.REJECTED: "Rejected",
    ComplaintStatus.REOPENED: "Reopened",
}


def complaint_image_path(instance, filename):
    """Never reuse the uploaded file name: it is attacker-controlled. Use a random name."""
    ext = os.path.splitext(filename)[1].lower()
    return f"complaints/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


class Complaint(models.Model):
    # PROTECT: a citizen with complaints cannot be deleted; deactivate the account instead.
    citizen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="complaints")
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=2000)
    status = models.CharField(max_length=25, choices=ComplaintStatus.choices, default=ComplaintStatus.SUBMITTED)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    # Set by the routing service (Phase 6); NULL until a department has been decided.
    department = models.ForeignKey("departments.Department", null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="complaints")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ---- AI routing (filled by complaints.services.routing; never by the browser)
    predicted_department = models.ForeignKey(
        "departments.Department", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="What the model suggested. Differs from `department` when a human corrected it.")
    ai_confidence = models.FloatField(null=True, blank=True)
    ai_probabilities = models.JSONField(default=dict, blank=True)
    ai_terms = models.JSONField(default=list, blank=True, help_text="Influential terms shown to staff")
    ai_model = models.ForeignKey("ml_engine.MLModel", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    ai_predicted_at = models.DateTimeField(null=True, blank=True)
    cleaned_text = models.TextField(blank=True)
    routing_method = models.CharField(max_length=10, choices=RoutingMethod.choices, blank=True)
    routing_reason = models.CharField(max_length=30, blank=True,
                                      help_text="Why the complaint was NOT auto-routed, if it was not")
    routed_at = models.DateTimeField(null=True, blank=True)

    resolution_photo = models.ImageField(upload_to=complaint_image_path, blank=True,
                                         help_text="Photo of the completed fix. Required before a complaint can be Resolved; "
                                                   "separate from the photo the citizen uploaded")
    resolved_at = models.DateTimeField(null=True, blank=True, help_text="When an officer verified the resolution")
    closed_at = models.DateTimeField(null=True, blank=True)

    # ---- escalation (the lifecycle status is NOT touched; see EscalationEvent)
    escalation_level = models.PositiveSmallIntegerField(default=0, help_text="0 none, 1 Department Head, 2 Administrator")
    sla_warned_at = models.DateTimeField(null=True, blank=True, help_text="When the 'approaching deadline' warning was sent")

    # ---- priority and service level
    priority_reason = models.CharField(max_length=120, blank=True, help_text="The rule that decided the priority")
    sla_deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(ai_confidence__isnull=True) | Q(ai_confidence__gte=0, ai_confidence__lte=1),
                                   name="cmp_ai_confidence_range"),
            models.CheckConstraint(condition=Q(escalation_level__gte=0, escalation_level__lte=2), name="cmp_escalation_level_range"),
        ]
        indexes = [
            models.Index(fields=["status", "sla_deadline"], name="cmp_status_sla_idx"),
            models.Index(fields=["department", "status"], name="cmp_dept_status_idx"),
            models.Index(fields=["status", "created_at"], name="cmp_status_created_idx"),
            models.Index(fields=["citizen", "created_at"], name="cmp_citizen_created_idx"),
        ]

    def __str__(self):
        return f"{self.reference}: {self.title}"

    @property
    def reference(self) -> str:
        return f"RL-{self.pk:06d}" if self.pk else "RL-(new)"

    @property
    def sla_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def sla_state(self, now=None):
        from ..sla import sla_state
        return sla_state(self.sla_deadline, now)

    @property
    def citizen_status_label(self) -> str:
        return CITIZEN_STATUS_LABELS.get(self.status, self.get_status_display())


class ComplaintLocation(models.Model):
    complaint = models.OneToOneField(Complaint, on_delete=models.CASCADE, related_name="location")
    area = models.ForeignKey("departments.Area", null=True, blank=True, on_delete=models.PROTECT,
                             related_name="complaint_locations")
    ward = models.ForeignKey("departments.Ward", null=True, blank=True, on_delete=models.PROTECT,
                             related_name="complaint_locations")
    street = models.CharField(max_length=150, blank=True)
    landmark = models.CharField(max_length=150, blank=True)
    building = models.CharField("house / building", max_length=150, blank=True)
    address_text = models.CharField("complete address", max_length=300)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # What the citizen selected, as issued by the location service (empty for complaints made before this existed).
    formatted_address = models.CharField(max_length=300, blank=True)
    place_id = models.CharField(max_length=80, blank=True)
    location_source = models.CharField(max_length=10, blank=True, help_text="SEARCH (picked from search results), MAP (pin) or GPS")

    class Meta:
        indexes = [models.Index(fields=["ward", "street"], name="loc_ward_street_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__isnull=True) | Q(latitude__gte=-90, latitude__lte=90),
                name="loc_latitude_range"),
            models.CheckConstraint(
                condition=Q(longitude__isnull=True) | Q(longitude__gte=-180, longitude__lte=180),
                name="loc_longitude_range"),
            models.CheckConstraint(
                condition=(Q(latitude__isnull=True, longitude__isnull=True)
                           | Q(latitude__isnull=False, longitude__isnull=False)),
                name="loc_gps_both_or_neither"),
        ]

    def __str__(self):
        return self.address_text or self.street or f"Location for {self.complaint.reference}"

    def save(self, *args, **kwargs):
        if self.ward_id and not self.area_id:
            self.area_id = self.ward.area_id
        super().save(*args, **kwargs)

    @property
    def has_gps(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class ImageKind(models.TextChoices):
    EVIDENCE = "EVIDENCE", "Citizen evidence"
    RESOLUTION = "RESOLUTION", "Resolution photo"


class ComplaintImage(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=complaint_image_path)
    kind = models.CharField(max_length=12, choices=ImageKind.choices, default=ImageKind.EVIDENCE)
    resolution = models.ForeignKey("complaints.Resolution", null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="images")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "id"]

    def __str__(self):
        return f"Image {self.pk} of {self.complaint.reference}"


class ComplaintStatusHistory(models.Model):
    """Append-only timeline. A status is never just overwritten (Phase 8 adds transition rules)."""

    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=25, blank=True)
    to_status = models.CharField(max_length=25, choices=ComplaintStatus.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp", "id"]
        verbose_name_plural = "status history"

    def __str__(self):
        return f"{self.complaint.reference}: {self.from_status or '-'} -> {self.to_status}"
