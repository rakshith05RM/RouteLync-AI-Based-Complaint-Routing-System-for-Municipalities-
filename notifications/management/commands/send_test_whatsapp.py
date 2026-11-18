"""python manage.py send_test_whatsapp 9876543210  : sends one WhatsApp message with the site's real settings."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from notifications import delivery


class Command(BaseCommand):
    help = "Send one test WhatsApp message to a mobile number, using exactly the settings the website uses."

    def add_arguments(self, parser):
        parser.add_argument("phone", help="10-digit mobile number (or international digits)")

    def handle(self, *args, **opts):
        self.stdout.write(f"Provider: {settings.WHATSAPP_PROVIDER}   switched on: {settings.NOTIFY_WHATSAPP_ENABLED}   "
                          f"settings complete: {delivery.whatsapp_configured()}")
        if not delivery.whatsapp_number(opts["phone"]):
            raise CommandError("That does not look like a valid mobile number.")
        out = delivery.Outgoing(0, "", False, opts["phone"], "This is a test message from RouteLync.", "/")
        try:
            delivery.send_whatsapp(out)
        except delivery.WhatsAppError as exc:
            raise CommandError(f"Not delivered: {exc}")
        self.stdout.write(self.style.SUCCESS("The provider accepted the message. If it does not arrive, see docs/NOTIFICATIONS.md (sandbox join / templates)."))
