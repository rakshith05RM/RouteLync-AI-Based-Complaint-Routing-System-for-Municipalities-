from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from audit.models import AuditLog
from audit.services import log_action
from complaints.models import Complaint, ComplaintStatus as S
from complaints.services import assign_worker, change_priority, route_complaint, start_work

from .helpers import AdminTestCase


class AuditLogTests(AdminTestCase):
    def test_log_action_records_who_what_and_target(self):
        entry = log_action(self.admin, "TEST_ACTION", target=self.complaint, summary="Something happened", details={"a": 1})
        self.assertEqual((entry.user, entry.action, entry.target_type, entry.target_id, entry.details), (self.admin, "TEST_ACTION", "Complaint", self.complaint.pk, {"a": 1}))
        self.assertEqual(log_action(None, "SYSTEM", summary="x").user, None)

    def test_staff_actions_on_complaints_are_logged_with_the_person(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        change_priority(self.complaint, "HIGH", actor=self.officer, reason="Near a school gate")
        entries = AuditLog.objects.filter(target_id=self.complaint.pk).order_by("id")
        self.assertEqual([(e.user.full_name, e.action) for e in entries],
                         [("Meera Nair", "COMPLAINT_STATUS"), ("Ravi Kumar", "COMPLAINT_STATUS"), ("Meera Nair", "COMPLAINT_EVENT")])
        self.assertIn("PENDING -> ASSIGNED_TO_WORKER", entries[0].summary)
        self.assertIn("Priority changed", entries[2].summary)

    def test_automatic_ai_steps_are_not_attributed_to_a_person(self):
        c = self.make(status=S.SUBMITTED, dept=None)
        route_complaint(c)
        self.assertFalse(AuditLog.objects.filter(action="COMPLAINT_STATUS", target_id=c.pk).exists())

    def test_citizen_actions_are_logged_too(self):
        from complaints.services import confirm_resolution
        c = self.make(status=S.RESOLVED)
        confirm_resolution(c, citizen=self.citizen)
        self.assertTrue(AuditLog.objects.filter(user=self.citizen, action="COMPLAINT_STATUS", summary__contains="RESOLVED -> CLOSED").exists())

    def test_failed_action_leaves_no_audit_entry(self):
        from complaints.services import WorkflowError
        before = AuditLog.objects.count()
        with self.assertRaises(WorkflowError):
            assign_worker(self.complaint, self.water_worker, actor=self.officer)
        self.assertEqual(AuditLog.objects.count(), before)

    def test_page_lists_filters_and_searches(self):
        log_action(self.admin, "SLA_CHANGED", summary="SLA hours changed")
        log_action(self.officer, "COMPLAINT_STATUS", summary="RL-000001: PENDING -> IN_PROGRESS")
        self.as_admin()
        names = lambda **p: [e.action for e in self.client.get(reverse("adminpanel:audit"), p).context["entries"] if e.action != "LOGIN"]
        self.assertCountEqual(names(), ["SLA_CHANGED", "COMPLAINT_STATUS"])
        self.assertEqual(names(action="SLA_CHANGED"), ["SLA_CHANGED"])
        self.assertEqual(names(q="IN_PROGRESS"), ["COMPLAINT_STATUS"])
        self.assertEqual(names(q="meera"), ["COMPLAINT_STATUS"])
        self.assertEqual(names(q="' OR 1=1 --"), [])
        self.assertContains(self.client.get(reverse("adminpanel:audit")), "Admin One")

    def test_pagination(self):
        for i in range(35):
            log_action(self.admin, "BULK", summary=f"entry {i}")
        self.as_admin()
        self.assertEqual(len(self.client.get(reverse("adminpanel:audit"), {"action": "BULK"}).context["entries"]), 30)
        self.assertEqual(len(self.client.get(reverse("adminpanel:audit"), {"action": "BULK", "page": 2}).context["entries"]), 5)

    def test_entries_cannot_be_edited_or_deleted_even_in_the_django_admin(self):
        from django.contrib import admin
        from audit.models import AuditLog as Model
        model_admin = admin.site._registry[Model]
        request = type("R", (), {"user": make_user("root@example.com", Role.ADMIN, is_superuser=True, is_staff=True)})()
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
