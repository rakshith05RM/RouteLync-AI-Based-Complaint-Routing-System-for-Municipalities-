from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Who did what, to which object, and when. Rows are only ever added, never edited."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=40, db_index=True)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp", "-id"]
        indexes = [models.Index(fields=["target_type", "target_id"], name="audit_target_idx")]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.action}: {self.summary[:60]}"
