from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import ComplaintStatus as S
from complaints.tests.workflow_helpers import WorkflowTestCase


class AdminTestCase(WorkflowTestCase):
    """Department fixtures from the workflow tests, plus an administrator."""

    def setUp(self):
        super().setUp()
        self.admin = make_user("admin@example.com", Role.ADMIN, full_name="Admin One")

    def as_admin(self):
        self.client.force_login(self.admin)

    def waiting(self, **kw):
        """A complaint in the verification queue, with the model's (low-confidence) suggestion stored."""
        kw.setdefault("title", "Something is wrong near the market")
        c = self.make(status=S.NEEDS_VERIFICATION, dept=None, confidence=0.4, **kw)
        c.predicted_department = self.elec
        c.routing_reason = "low_confidence"
        c.save()
        return c
