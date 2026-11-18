from django.core.management.base import BaseCommand

from complaints.services.attempts import purge_old_attempts


class Command(BaseCommand):
    help = "Delete rejected-submission drafts (and their photos) older than ATTEMPT_RETENTION_DAYS."

    def handle(self, *args, **opts):
        self.stdout.write(self.style.SUCCESS(f"Removed {purge_old_attempts()} old draft(s)."))
