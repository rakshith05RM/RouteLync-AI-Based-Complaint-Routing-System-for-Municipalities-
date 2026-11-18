"""Sending a notification outside the app, by email and WhatsApp.

The in-app notification is always created first (see services.notify). Delivery is best-effort on top of it:
  * it runs only after the database transaction commits, so a rolled-back action never sends a message;
  * it runs in a background thread (NOTIFY_ASYNC) so a slow mail server or WhatsApp provider cannot slow a page;
  * a failure on one channel never affects the other channel or the request, and is logged without
    addresses, phone numbers, message text or credentials.
Nothing here reads the database inside the thread: everything needed is copied into `Outgoing` first.
"""
import base64
import json
import logging
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils.html import format_html

from core.mailer import send_routelync_email

logger = logging.getLogger("routelync")


class WhatsAppError(Exception):
    """Raised with a short, secret-free reason; the send_test_whatsapp command prints it."""


@dataclass(frozen=True)
class Outgoing:
    user_id: int
    email: str
    email_verified: bool
    phone: str
    message: str
    link: str


def full_url(link):
    """Site-relative links only (never an arbitrary address) are turned into absolute ones."""
    return f"{settings.SITE_URL}{link}" if link and link.startswith("/") and not link.startswith("//") else settings.SITE_URL


def whatsapp_number(phone):
    """The 10-digit mobile on file becomes international digits (919876543210). Returns "" if it cannot be one."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        digits = f"{settings.WHATSAPP_COUNTRY_CODE}{digits}"
    return digits if 11 <= len(digits) <= 15 else ""


# ------------------------------------------------------------------ entry point
def schedule(user, message, link=""):
    """Called by notifications.services.notify for every notification."""
    if not (settings.NOTIFY_EMAIL_ENABLED or settings.NOTIFY_WHATSAPP_ENABLED):
        return
    if user.role not in settings.NOTIFY_EXTERNAL_ROLES:
        return
    out = Outgoing(user.pk, user.email or "", bool(user.email_verified), user.phone or "", message, link)
    transaction.on_commit(lambda: _start(out))


def _start(out):
    if settings.NOTIFY_ASYNC:
        threading.Thread(target=deliver, args=(out,), daemon=True, name="notify-delivery").start()
    else:
        deliver(out)


def deliver(out):
    if settings.NOTIFY_EMAIL_ENABLED:
        try:
            send_email(out)
        except Exception as exc:                       # delivery must never break the caller
            logger.error("Notification email to user %s failed: %s", out.user_id, exc.__class__.__name__)
    if settings.NOTIFY_WHATSAPP_ENABLED:
        try:
            send_whatsapp(out)
        except WhatsAppError as exc:
            logger.error("Notification WhatsApp to user %s failed: %s", out.user_id, exc)
        except Exception as exc:
            logger.error("Notification WhatsApp to user %s failed: %s", out.user_id, exc.__class__.__name__)


# ------------------------------------------------------------------ email
def send_email(out):
    if not out.email or not out.email_verified:
        return False
    subject = " ".join(f"RouteLync: {out.message}".split())[:150]
    url = full_url(out.link)
    body = (f"{out.message}\n\nTrack this complaint: {url}\n\n"
            "You are receiving this because you have a RouteLync account. Sign in to see every update.\n")
    html_body = format_html(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
        '</head><body style="margin:0;padding:24px;font-family:Arial,sans-serif;line-height:1.5;color:#17212b">'
        '<main style="max-width:560px;margin:0 auto"><p>{}</p>'
        '<p><a href="{}" style="display:inline-block;padding:12px 18px;border-radius:6px;'
        'background:#176b57;color:#fff;text-decoration:none">Track this complaint</a></p>'
        '<p style="font-size:14px;color:#53616d">You are receiving this because you have a RouteLync account. '
        'Sign in to see every update.</p></main></body></html>',
        out.message, url)
    send_routelync_email(subject, body, [out.email], html_message=str(html_body))
    return True


# ------------------------------------------------------------------ WhatsApp
def whatsapp_configured():
    if settings.WHATSAPP_PROVIDER == "meta":
        return bool(settings.META_WHATSAPP_TOKEN and settings.META_WHATSAPP_PHONE_ID)
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM)


def send_whatsapp(out):
    to = whatsapp_number(out.phone)
    if not to:
        return False
    if not whatsapp_configured():
        raise WhatsAppError("WhatsApp is switched on but the provider settings are incomplete")
    text = f"RouteLync: {out.message}\n{full_url(out.link)}"
    if settings.WHATSAPP_PROVIDER == "meta":
        _send_meta(to, text)
    elif settings.WHATSAPP_PROVIDER == "twilio":
        _send_twilio(to, text)
    else:
        raise WhatsAppError("WHATSAPP_PROVIDER must be 'twilio' or 'meta'")
    return True


def _post(request):
    try:
        with urllib.request.urlopen(request, timeout=settings.WHATSAPP_TIMEOUT) as response:   # fixed https hosts only
            if not 200 <= response.status < 300:
                raise WhatsAppError(f"provider answered HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise WhatsAppError(f"provider rejected the message (HTTP {exc.code})") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise WhatsAppError("could not reach the provider (network or timeout)") from None


def _send_twilio(to_digits, text):
    sid = settings.TWILIO_ACCOUNT_SID
    sender = settings.TWILIO_WHATSAPP_FROM.lstrip("+")
    data = urllib.parse.urlencode({"From": f"whatsapp:+{sender}", "To": f"whatsapp:+{to_digits}", "Body": text}).encode()
    request = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(sid)}/Messages.json", data=data, method="POST")
    token = base64.b64encode(f"{sid}:{settings.TWILIO_AUTH_TOKEN}".encode()).decode()
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    _post(request)


def _send_meta(to_digits, text):
    if settings.WHATSAPP_TEMPLATE_NAME:
        # Business-initiated messages must use a template approved by Meta. Template variables cannot hold line breaks.
        payload = {"messaging_product": "whatsapp", "to": to_digits, "type": "template", "template": {
            "name": settings.WHATSAPP_TEMPLATE_NAME, "language": {"code": settings.WHATSAPP_TEMPLATE_LANG},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": " ".join(text.split())}]}]}}
    else:
        # Free-form text is only delivered inside the 24-hour window after the person last messaged your number.
        payload = {"messaging_product": "whatsapp", "to": to_digits, "type": "text", "text": {"body": text, "preview_url": True}}
    request = urllib.request.Request(f"https://graph.facebook.com/v20.0/{urllib.parse.quote(settings.META_WHATSAPP_PHONE_ID)}/messages",
                                     data=json.dumps(payload).encode(), method="POST")
    request.add_header("Authorization", f"Bearer {settings.META_WHATSAPP_TOKEN}")
    request.add_header("Content-Type", "application/json")
    _post(request)
