from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import ComplaintStatus as S

from .officer_helpers import OfficerTestCase


class WorkflowTestCase(OfficerTestCase):
    """Adds field workers and a complaint that is already in the department queue."""

    def setUp(self):
        super().setUp()
        self.worker = make_user("worker1@example.com", Role.FIELD_WORKER, department=self.elec, full_name="Ravi Kumar")
        self.worker2 = make_user("worker2@example.com", Role.FIELD_WORKER, department=self.elec, full_name="Manoj Shetty")
        self.water_worker = make_user("water.worker@example.com", Role.FIELD_WORKER, department=self.water, full_name="Lakshmi Devi")
        self.complaint = self.make(title="Streetlight not working", status=S.PENDING)

    def as_officer(self):
        self.client.force_login(self.officer)

    def as_worker(self, worker=None):
        self.client.force_login(worker or self.worker)

    def as_citizen(self):
        self.client.force_login(self.citizen)

    def fresh(self):
        self.complaint.refresh_from_db()
        return self.complaint

    def history(self):
        return list(self.complaint.status_history.values_list("to_status", flat=True))
