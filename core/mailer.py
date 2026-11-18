"""Shared RouteLync email sender configuration."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_routelync_email(subject, body, recipients, *, from_email=None, html_message=None):
    reply_to = [settings.DEFAULT_REPLY_TO_EMAIL] if settings.DEFAULT_REPLY_TO_EMAIL else []
    message = EmailMultiAlternatives(
        subject,
        body,
        from_email or settings.DEFAULT_FROM_EMAIL,
        recipients,
        reply_to=reply_to,
    )
    if html_message is not None:
        message.attach_alternative(html_message, "text/html")
    return message.send(fail_silently=False)
