from django.core.management.base import BaseCommand

from complaints.models import Complaint, ComplaintStatus
from complaints.services.routing import route_complaint


class Command(BaseCommand):
    help = "Route complaints stuck in SUBMITTED (for example after an outage during submission)."

    def handle(self, *args, **opts):
        routed = failed = 0
        for complaint in Complaint.objects.filter(status=ComplaintStatus.SUBMITTED).order_by("created_at"):
            try:
                outcome = route_complaint(complaint)
                routed += 1
                self.stdout.write(f"{complaint.reference}: {outcome.status}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.stderr.write(f"{complaint.reference}: FAILED ({exc})")
        self.stdout.write(self.style.SUCCESS(f"Done. routed={routed} failed={failed}"))
