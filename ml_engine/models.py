import hashlib

from django.conf import settings
from django.db import models, transaction


class TrainingSample(models.Model):
    """
    One labelled complaint text. Only rows with is_verified=True are ever used for training:
    unverified citizen complaints never become training data automatically.
    """

    class Source(models.TextChoices):
        SYNTHETIC = "SYNTHETIC", "Synthetic (generated)"
        IMPORTED = "IMPORTED", "Imported dataset"
        VERIFIED_COMPLAINT = "VERIFIED_COMPLAINT", "Verified real complaint"

    text = models.TextField(max_length=2000)
    # sha256 of the normalised text: enforces "no duplicate training texts" at database level.
    text_hash = models.CharField(max_length=64, unique=True, editable=False)
    department = models.ForeignKey("departments.Department", on_delete=models.PROTECT, related_name="training_samples")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.IMPORTED)
    is_verified = models.BooleanField(default=False, db_index=True)
    dataset_version = models.CharField(max_length=40, blank=True)
    complaint = models.ForeignKey("complaints.Complaint", null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="training_samples")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"[{self.department.code}] {self.text[:60]}"

    @staticmethod
    def hash_text(text: str) -> str:
        normalised = " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        self.text_hash = self.hash_text(self.text)
        super().save(*args, **kwargs)


class MLModel(models.Model):
    """Registry of every trained model with its measured evaluation. Exactly one is active."""

    version = models.PositiveIntegerField(unique=True)
    artefact_file = models.CharField(max_length=255, help_text="File name inside ML_MODELS_DIR")
    artefact_sha256 = models.CharField(max_length=64, help_text="Integrity check before loading")
    labels = models.JSONField(help_text="Department codes in the model's class order")

    # dataset
    dataset_size = models.PositiveIntegerField()
    train_size = models.PositiveIntegerField()
    test_size = models.PositiveIntegerField()
    class_distribution = models.JSONField()

    # held-out TEST split evaluation
    accuracy = models.FloatField()
    precision_macro = models.FloatField()
    recall_macro = models.FloatField()
    f1_macro = models.FloatField()
    per_class_metrics = models.JSONField()
    confusion_matrix = models.JSONField()

    # separate hand-written challenge set (never trained on); null if the file was absent
    challenge_accuracy = models.FloatField(null=True, blank=True)
    challenge_report = models.JSONField(null=True, blank=True)

    # training configuration and confidence threshold
    best_params = models.JSONField()
    cv_f1_macro = models.FloatField()
    conf_threshold = models.FloatField(help_text="Below this, a complaint needs human verification")
    threshold_analysis = models.JSONField()

    is_active = models.BooleanField(default=False)
    trained_at = models.DateTimeField(auto_now_add=True)
    trained_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-version"]
        verbose_name = "ML model"

    def __str__(self):
        return f"Model v{self.version}" + (" (active)" if self.is_active else "")

    @transaction.atomic
    def activate(self, user=None):
        """Make this the only active model. Done in code because MySQL has no partial unique index."""
        MLModel.objects.select_for_update().filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        self.is_active = True
        self.save(update_fields=["is_active"])
        from audit.services import log_action
        log_action(user, "MODEL_ACTIVATED", target=self, summary=f"Model v{self.version} activated")
        from .model_manager import clear_cache
        clear_cache()
