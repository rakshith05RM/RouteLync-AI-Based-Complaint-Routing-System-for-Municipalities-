"""
Manual check of REAL email delivery:   python manage.py send_test_email you@example.com
It uses exactly the settings the website uses, so if this email reaches your inbox, verification codes and
password-reset emails will too. Passwords are never printed.
"""
import socket

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.mailer import send_routelync_email


class Command(BaseCommand):
    help = "Send a test email using the website's email settings."

    def add_arguments(self, parser):
        parser.add_argument("to")

    def handle(self, *args, **opts):
        backend = settings.EMAIL_BACKEND
        self.stdout.write(f"Backend: {backend}")
        self.stdout.write(f"Server: {settings.EMAIL_HOST or '(none)'}:{settings.EMAIL_PORT}  TLS={settings.EMAIL_USE_TLS} SSL={settings.EMAIL_USE_SSL}  user={'set' if settings.EMAIL_HOST_USER else 'EMPTY'}  password={'set' if settings.EMAIL_HOST_PASSWORD else 'EMPTY'}")
        if "console" in backend:
            self.stdout.write(self.style.WARNING("This is the development console backend: the message is printed below and NOT delivered to any inbox."))
        try:
            send_routelync_email("RouteLync test email", "If you can read this, RouteLync can send email.", [opts["to"]])
        except (OSError, socket.timeout) as exc:
            raise CommandError(f"Sending failed ({exc.__class__.__name__}: {exc}). Check host, port, TLS/SSL, username and password.")
        except Exception as exc:  # noqa: BLE001 - SMTP authentication and protocol errors
            raise CommandError(f"Sending failed ({exc.__class__.__name__}): {exc}")
        self.stdout.write(self.style.SUCCESS(f"The mail server accepted the message for {opts['to']}. Now check the inbox (and spam)."))
