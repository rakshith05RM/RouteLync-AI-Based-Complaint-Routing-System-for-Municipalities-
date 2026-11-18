import os
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def attempt_image_path(instance, filename):
    return f"attempts/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


class SubmissionAttempt(models.Model):
    """
    A submission that was NOT accepted because the description was unclear, irrelevant or outside the supported
    categories. It is a draft so the citizen can correct it without retyping; it is NOT a complaint: it has no
    reference number, is never routed, and is never counted in any complaint statistic.
    """

    citizen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submission_attempts")
    title = models.CharField(max_length=120, blank=True)
    description = models.TextField(max_length=2000, blank=True)
    area = models.ForeignKey("departments.Area", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    ward = models.ForeignKey("departments.Ward", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    ward_text = models.CharField(max_length=100, blank=True)
    street = models.CharField(max_length=150, blank=True)
    landmark = models.CharField(max_length=150, blank=True)
    building = models.CharField(max_length=150, blank=True)
    address_text = models.CharField(max_length=300, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    image = models.ImageField(upload_to=attempt_image_path, blank=True)
    reason_code = models.CharField(max_length=20)
    reason_label = models.CharField(max_length=60)
    message = models.CharField(max_length=400)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["citizen", "updated_at"], name="attempt_citizen_idx")]

    def __str__(self):
        return f"Not submitted ({self.reason_code}) by user {self.citizen_id}"
