from django.conf import settings
from django.db import models


class Notification(models.Model):
    """An in-app message for one person. (Email and WhatsApp copies are sent by notifications.delivery.)"""

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=40, blank=True)
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=200, blank=True, help_text="Site-relative path to open")
    complaint = models.ForeignKey("complaints.Complaint", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "is_read", "created_at"], name="notif_recipient_idx")]

    def __str__(self):
        return f"To {self.recipient_id}: {self.message[:50]}"
