"""
Master data for departments, geography (Area -> Ward), staff profiles and SLA settings.

Design notes
  * Department is a table, not a hard-coded list, so "Parks" can be added later without code
    changes. Department.code is the label the ML model predicts.
  * Area -> Ward is a real hierarchy, so ward numbers can be validated against a known list.
  * Officer / field-worker data lives in profile tables (OneToOne to User) instead of extra
    nullable columns on the user table.
  * "One head per department" is enforced in clean()/save() rather than a conditional unique
    constraint, because MySQL does not support partial (conditional) unique indexes.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from accounts.models import Role


class Priority(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    CRITICAL = "CRITICAL", "Critical"


class Department(models.Model):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(
        max_length=30, unique=True,
        validators=[RegexValidator(r"^[A-Z][A-Z0-9_]{1,29}$", "Use upper-case letters, digits and underscores, e.g. WATER_SUPPLY.")],
        help_text="Class label used by the ML model. Treat as permanent once a model has been trained.",
    )
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Area(models.Model):
    class ServiceDistrict(models.TextChoices):
        BENGALURU_URBAN = "Bengaluru Urban", "Bengaluru Urban"
        BENGALURU_RURAL = "Bengaluru Rural", "Bengaluru Rural"

    name = models.CharField(max_length=100, unique=True)
    service_district = models.CharField(max_length=20, choices=ServiceDistrict.choices, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ward(models.Model):
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="wards")
    number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    name = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["area__name", "number"]
        constraints = [
            models.UniqueConstraint(fields=["area", "number"], name="uniq_ward_number_per_area"),
            models.CheckConstraint(condition=Q(number__gte=1), name="ward_number_positive"),
        ]

    def __str__(self):
        return f"Ward {self.number} ({self.area.name})"


class _StaffProfileBase(models.Model):
    """Shared behaviour: the linked user must have the matching role."""

    required_role: str = ""

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.user_id and self.user.role != self.required_role:
            raise ValidationError({"user": f"This user's role must be '{Role(self.required_role).label}'."})

    def save(self, *args, **kwargs):
        self.full_clean()  # enforce the rules above even outside forms (shell, scripts, seed)
        super().save(*args, **kwargs)


class OfficerProfile(_StaffProfileBase):
    required_role = Role.OFFICER

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="officer_profile", limit_choices_to={"role": Role.OFFICER})
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="officers")
    designation = models.CharField(max_length=100, blank=True)
    is_department_head = models.BooleanField(default=False)

    def clean(self):
        super().clean()
        if self.is_department_head and self.department_id:
            clash = OfficerProfile.objects.filter(department=self.department, is_department_head=True)
            if self.pk:
                clash = clash.exclude(pk=self.pk)
            if clash.exists():
                raise ValidationError({"is_department_head": "This department already has a head."})

    def __str__(self):
        return f"{self.user.full_name} - {self.department.name}"


class FieldWorkerProfile(_StaffProfileBase):
    required_role = Role.FIELD_WORKER

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="worker_profile", limit_choices_to={"role": Role.FIELD_WORKER})
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="field_workers")
    employee_code = models.CharField(max_length=20, unique=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.full_name} ({self.employee_code})"


class SLAConfiguration(models.Model):
    """Hours allowed to resolve a complaint of each priority. Editable by administrators."""

    priority = models.CharField(max_length=10, choices=Priority.choices, unique=True)
    hours = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = "SLA configuration"
        constraints = [models.CheckConstraint(condition=Q(hours__gte=1), name="sla_hours_positive")]

    def __str__(self):
        return f"{self.get_priority_display()}: {self.hours} h"
