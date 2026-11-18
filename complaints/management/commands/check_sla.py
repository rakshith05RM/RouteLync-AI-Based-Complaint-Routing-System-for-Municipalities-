from django.core.management.base import BaseCommand

from complaints.services import run_sla_check


class Command(BaseCommand):
    help = ("Send 'approaching deadline' warnings and escalate overdue complaints. Safe to run repeatedly; "
            "schedule it every 5-15 minutes (cron on Linux, Task Scheduler on Windows).")

    def handle(self, *args, **opts):
        result = run_sla_check()
        self.stdout.write(self.style.SUCCESS(result.summary()))
