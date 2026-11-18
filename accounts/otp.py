"""
Email verification codes.

  * 6 random digits from the operating system's secure generator (never hard-coded, never logged);
  * only an HMAC of the code is stored, so a database leak does not reveal live codes;
  * a code expires, works once, and allows a limited number of wrong guesses;
  * new codes are subject to a cooldown and an hourly cap, and issuing a new code cancels the old one.
"""
import hmac
import secrets
from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import EmailOTP


class OTPCooldown(Exception):
    def __init__(self, seconds_left: int):
        super().__init__(f"Wait {seconds_left} seconds before asking for another code.")
        self.seconds_left = seconds_left


class OTPRateLimited(Exception):
    pass


def _hash(user_id: int, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"otp:{user_id}:{code}".encode(), sha256).hexdigest()


@transaction.atomic
def issue_otp(user) -> str:
    """Create a fresh code for `user` and return it (the caller emails it). Raises OTPCooldown / OTPRateLimited."""
    now = timezone.now()
    recent = list(EmailOTP.objects.select_for_update().filter(user=user, created_at__gte=now - timedelta(hours=1)))
    if recent:
        wait = settings.OTP_RESEND_COOLDOWN_SECONDS - (now - max(o.created_at for o in recent)).total_seconds()
        if wait > 0:
            raise OTPCooldown(int(wait) + 1)
    if len(recent) >= settings.OTP_MAX_SENDS_PER_HOUR:
        raise OTPRateLimited("Too many codes were requested. Please try again later.")
    EmailOTP.objects.filter(user=user, used_at__isnull=True).update(used_at=now)        # the old code is cancelled
    code = f"{secrets.randbelow(10 ** 6):06d}"
    EmailOTP.objects.create(user=user, code_hash=_hash(user.pk, code), created_at=now,
                            expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES))
    return code


@transaction.atomic
def verify_otp(user, code: str) -> bool:
    """True and the account is marked verified only if `code` is the live, unused, unexpired code."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    now = timezone.now()
    otp = (EmailOTP.objects.select_for_update().filter(user=user, used_at__isnull=True, expires_at__gt=now)
           .order_by("-created_at").first())
    if otp is None or otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        return False
    otp.attempts += 1
    if len(code) != 6 or not hmac.compare_digest(_hash(user.pk, code), otp.code_hash):
        otp.save(update_fields=["attempts"])
        return False
    otp.used_at = now
    otp.save(update_fields=["attempts", "used_at"])
    user.email_verified = True
    user.save(update_fields=["email_verified", "updated_at"])
    return True
