from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from accounts.models import Role
from accounts.tests.helpers import make_department, make_user
from complaints.models import Complaint, ComplaintLocation, ComplaintStatus as S
from departments.models import Area, Priority, Ward

from .helpers import ComplaintTestCase


class OfficerTestCase(ComplaintTestCase):
    """Two departments, two officers, several wards, and a helper that builds routed complaints directly."""

    def setUp(self):
        super().setUp()
        self.elec = make_department("ELECTRICITY")
        self.water = make_department("WATER_SUPPLY")
        self.officer = make_user("officer@example.com", Role.OFFICER, department=self.elec, full_name="Meera Nair")
        self.water_officer = make_user("water.officer@example.com", Role.OFFICER, department=self.water)
        self.ward2 = Ward.objects.get_or_create(area=self.area, number=155)[0]
        self.counter = 0

    def make(self, *, dept="default", title=None, description="The problem has been there for some days now.", ward=None,
             street="4th Main Road", priority=Priority.MEDIUM, status=S.PENDING, hours_ago=1, sla_hours=24,
             confidence=0.9, lat=None, lng=None, citizen=None, landmark=""):
        self.counter += 1
        dept = self.elec if dept == "default" else dept
        now = timezone.now()
        created = now - timedelta(hours=hours_ago)
        c = Complaint.objects.create(
            citizen=citizen or self.citizen, title=title or f"Complaint number {self.counter}", description=description,
            status=status, priority=priority, department=dept, ai_confidence=confidence,
            sla_deadline=created + timedelta(hours=sla_hours))
        Complaint.objects.filter(pk=c.pk).update(created_at=created)
        ComplaintLocation.objects.create(
            complaint=c, ward=ward or self.ward, street=street, landmark=landmark, address_text=f"{street}, test address",
            latitude=None if lat is None else Decimal(str(lat)), longitude=None if lng is None else Decimal(str(lng)))
        c.refresh_from_db()
        return c

    def login_officer(self):
        self.client.force_login(self.officer)
