"""
Custom user model for RouteLync.

Why a custom model?
  * One login identity (email) for every role -> the "single website" requirement.
  * A `role` field lets Django route each person to the right dashboard after login.
  * It must exist BEFORE the first migration; changing AUTH_USER_MODEL later is painful.

Role-specific data (department, employee code, address) lives in separate profile
tables added in Phases 2-3, which keeps this table small and normalised.
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from core.validators import mobile_number_validator


class Role(models.TextChoices):
    CITIZEN = "CITIZEN", "Citizen"
    OFFICER = "OFFICER", "Department Officer"
    FIELD_WORKER = "FIELD_WORKER", "Field Worker"
    ADMIN = "ADMIN", "Administrator"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).strip().lower()  # case-insensitive uniqueness
        user = self.model(email=email, **extra)
        user.set_password(password)  # hashed (PBKDF2 by default), never stored in plain text
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, username):
        # authenticate() calls this. iexact keeps login case-insensitive on every database.
        return self.get(email__iexact=username.strip())

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", Role.CITIZEN)
        extra.setdefault("email_verified", True)       # accounts made by staff/scripts are trusted; self-registration passes False
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", Role.ADMIN)
        extra.setdefault("email_verified", True)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra["is_staff"] is not True or extra["is_superuser"] is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("email address", unique=True, max_length=254)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(
        "mobile number", max_length=10, blank=True, validators=[mobile_number_validator]
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CITIZEN, db_index=True)

    is_active = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False, help_text="The person has proved they control this address")
    is_staff = models.BooleanField(default=False, help_text="Can sign in to the Django admin site.")
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["full_name"]
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email

    # Convenience role checks used by permission mixins from Phase 2 onwards.
    @property
    def is_citizen(self):
        return self.role == Role.CITIZEN

    @property
    def is_officer(self):
        return self.role == Role.OFFICER

    @property
    def is_field_worker(self):
        return self.role == Role.FIELD_WORKER

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN


class CitizenProfile(models.Model):
    """Citizen-only data, kept out of the auth table (normalisation)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="citizen_profile")
    address = models.TextField(blank=True, max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Citizen profile of {self.user.email}"


class EmailOTP(models.Model):
    """A one-time email verification code. Only a keyed hash of the code is stored, never the code itself."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_otps")
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "created_at"], name="otp_user_created_idx")]

    def __str__(self):
        return f"OTP for user {self.user_id} ({'used' if self.used_at else 'open'})"
