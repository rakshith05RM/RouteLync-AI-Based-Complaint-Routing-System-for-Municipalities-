"""Deployment check: make sure real email delivery is configured, otherwise citizens never receive their codes."""
from django.conf import settings
from django.core import checks

NOT_REAL = ("console", "locmem", "dummy", "filebased")


@checks.register(checks.Tags.security, deploy=True)
def email_is_configured(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    backend = settings.EMAIL_BACKEND
    if any(word in backend for word in NOT_REAL):
        return [checks.Warning("EMAIL_BACKEND is a development backend. Verification codes and password-reset emails will not reach citizens.",
                               hint="Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and the EMAIL_HOST settings (see docs/EMAIL_SETUP.md).",
                               id="routelync.W001")]
    if "smtp" in backend and not (settings.EMAIL_HOST and settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD):
        return [checks.Warning("SMTP email is selected but EMAIL_HOST, EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is empty.",
                               hint="Fill in the email settings in .env (see docs/EMAIL_SETUP.md).", id="routelync.W002")]
    return []
