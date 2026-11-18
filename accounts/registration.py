"""
Self-registration with email verification.

Three situations, all of which lead to the SAME page for the visitor so the form cannot be used to discover
which email addresses already have accounts:
  new address            -> pending account + verification code emailed
  pending (unverified)   -> details replaced by the newest submission + a new code (only the mailbox owner can verify)
  already verified       -> nothing changes; the owner is emailed a notice
"""
import logging
from dataclasses import dataclass

from django.db import transaction

from . import emails
from .models import CitizenProfile, Role, User
from .otp import OTPCooldown, OTPRateLimited, issue_otp

logger = logging.getLogger("routelync")


@dataclass
class RegistrationResult:
    kind: str                 # "new", "pending", "existing"
    delivery_failed: bool = False


def _send_code(user) -> bool:
    """True if a code was emailed. A cooldown or hourly cap is not a failure (an earlier email is still valid)."""
    try:
        code = issue_otp(user)
    except (OTPCooldown, OTPRateLimited):
        return True
    try:
        emails.send_verification_code(user, code)
        return True
    except emails.EmailDeliveryError:
        return False


def register_citizen(data) -> RegistrationResult:
    email = data["email"].strip().lower()
    existing = User.objects.filter(email__iexact=email).first()

    if existing is not None and (existing.email_verified or existing.role != Role.CITIZEN):
        try:
            emails.send_account_exists_notice(existing)
        except emails.EmailDeliveryError:
            logger.warning("Could not send the account-exists notice for user %s", existing.pk)
        return RegistrationResult("existing")

    with transaction.atomic():
        if existing is None:
            user = User.objects.create_user(email=email, password=data["password1"], full_name=data["full_name"],
                                            phone=data["phone"], role=Role.CITIZEN, email_verified=False)
            kind = "new"
        else:
            user = existing
            user.full_name, user.phone = data["full_name"], data["phone"]
            user.set_password(data["password1"])
            user.save()
            kind = "pending"
        profile, _ = CitizenProfile.objects.get_or_create(user=user)
        profile.address = (data.get("address") or "").strip()
        profile.save(update_fields=["address"])
    return RegistrationResult(kind, delivery_failed=not _send_code(user))
