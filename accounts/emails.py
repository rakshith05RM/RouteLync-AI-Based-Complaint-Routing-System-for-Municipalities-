"""Sending the account emails. A failure is reported to the caller; it is never silently ignored."""
import logging
import smtplib

from django.conf import settings
from django.template.loader import render_to_string

from core.mailer import send_routelync_email

logger = logging.getLogger("routelync")


class EmailDeliveryError(Exception):
    pass


def _send(user, subject_template, body_template, context=None):
    ctx = {"user": user, "site_name": "RouteLync", **(context or {})}
    subject = " ".join(render_to_string(subject_template, ctx).split())
    body = render_to_string(body_template, ctx)
    try:
        sent = send_routelync_email(subject, body, [user.email])
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:       # includes connection refused and timeouts
        logger.error("Email to user %s failed: %s", user.pk, exc.__class__.__name__)
        raise EmailDeliveryError(str(exc)) from exc
    if not sent:
        raise EmailDeliveryError("The mail backend did not accept the message.")


def send_verification_code(user, code):
    _send(user, "accounts/email/verify_subject.txt", "accounts/email/verify_body.txt",
          {"code": code, "minutes": settings.OTP_TTL_MINUTES})


def send_account_exists_notice(user):
    _send(user, "accounts/email/exists_subject.txt", "accounts/email/exists_body.txt")


def send_password_changed_notice(user):
    _send(user, "accounts/email/changed_subject.txt", "accounts/email/changed_body.txt")
