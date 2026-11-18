from django.conf import settings
from django.db import models


class RoutingCorrection(models.Model):
    """
    A human decision about which department should handle a complaint. This is the feedback loop:
    prediction -> human verification -> correct label -> (optionally) verified training sample.
    """

    complaint = models.ForeignKey("complaints.Complaint", on_delete=models.CASCADE, related_name="routing_corrections")
    predicted_department = models.ForeignKey("departments.Department", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    corrected_department = models.ForeignKey("departments.Department", on_delete=models.PROTECT, related_name="+")
    corrected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    ai_was_correct = models.BooleanField(help_text="The administrator confirmed the model's suggestion")
    was_unrouted = models.BooleanField(help_text="The complaint was waiting in the verification queue")
    note = models.CharField(max_length=255, blank=True)
    training_sample = models.ForeignKey("ml_engine.TrainingSample", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.complaint.reference}: {self.predicted_department} -> {self.corrected_department}"
