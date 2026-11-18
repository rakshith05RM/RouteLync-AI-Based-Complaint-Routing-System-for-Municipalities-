import io
from datetime import timedelta

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import Complaint, ComplaintStatus as S, EscalationEvent
from complaints.services import (WorkflowError, assign_worker, change_priority, escalate_complaint, reopen_complaint,
                                 run_sla_check)
from departments.models import OfficerProfile, Priority
from notifications.models import Notification

from .workflow_helpers import WorkflowTestCase


class SlaCheckTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.head = make_user("head@example.com", Role.OFFICER, department=self.elec, full_name="Gopal Hegde")
        OfficerProfile.objects.filter(user=self.head).update(is_department_head=True)
        self.admin = make_user("admin@example.com", Role.ADMIN, full_name="Admin One")
        Complaint.objects.filter(pk=self.complaint.pk).update(status=S.CLOSED)      # keep these tests about their own complaints
        self.now = timezone.now()

    def complaint_with(self, hours_ago, sla_hours, **kw):
        return self.make(hours_ago=hours_ago, sla_hours=sla_hours, **kw)

    def kinds(self, user):
        return list(Notification.objects.filter(recipient=user).values_list("kind", flat=True))

    # ---- warnings
    def test_warning_sent_once_when_a_quarter_of_the_window_is_left(self):
        c = self.complaint_with(hours_ago=19, sla_hours=24)             # 5 h left of 24 h (> 25%? no: 5/24 = 21%)
        result = run_sla_check(self.now)
        self.assertEqual(result.warned, 1)
        c.refresh_from_db()
        self.assertIsNotNone(c.sla_warned_at)
        self.assertIn("SLA_WARNING", self.kinds(self.officer))
        self.assertIn("approaching its deadline", Notification.objects.filter(kind="SLA_WARNING").first().message)
        self.assertEqual(run_sla_check(self.now).warned, 0)             # not sent again

    def test_no_warning_when_plenty_of_time_is_left(self):
        self.complaint_with(hours_ago=2, sla_hours=24)
        self.assertEqual(run_sla_check(self.now).warned, 0)
        self.assertFalse(Notification.objects.filter(kind="SLA_WARNING").exists())

    def test_finished_or_unrouted_complaints_get_no_warning(self):
        for status in (S.RESOLVED, S.CLOSED, S.REJECTED):
            self.complaint_with(hours_ago=22, sla_hours=24, status=status)
        self.assertEqual(run_sla_check(self.now).warned, 0)

    def test_priority_change_allows_a_new_warning(self):
        c = self.complaint_with(hours_ago=19, sla_hours=24)
        run_sla_check(self.now)
        change_priority(c, Priority.LOW, actor=self.officer, reason="Not dangerous after all")
        c.refresh_from_db()
        self.assertIsNone(c.sla_warned_at)

    # ---- level 1
    def test_overdue_complaint_is_escalated_to_the_department_head(self):
        c = self.complaint_with(hours_ago=30, sla_hours=24)
        result = run_sla_check(self.now)
        self.assertEqual(result.level1, 1)
        c.refresh_from_db()
        self.assertEqual((c.escalation_level, c.status), (1, S.PENDING))                 # status is NOT overwritten
        event = EscalationEvent.objects.get()
        self.assertEqual((event.level, event.escalated_to, event.automatic, event.triggered_by), (1, self.head, True, None))
        self.assertIn("SLA deadline passed", event.reason)
        self.assertIn("ESCALATED", self.kinds(self.head))
        self.assertIn("Escalated to Department Head", c.status_history.last().note)
        self.assertEqual(run_sla_check(self.now).level1, 0)                             # idempotent

    def test_escalation_does_not_block_the_work(self):
        c = self.complaint_with(hours_ago=30, sla_hours=24)
        run_sla_check(self.now)
        assign_worker(c, self.worker, actor=self.officer)                               # still assignable
        c.refresh_from_db()
        self.assertEqual((c.status, c.escalation_level), (S.ASSIGNED_TO_WORKER, 1))

    def test_without_a_head_the_officers_and_administrators_are_told(self):
        OfficerProfile.objects.filter(user=self.head).update(is_department_head=False)
        self.complaint_with(hours_ago=30, sla_hours=24)
        run_sla_check(self.now)
        self.assertEqual(EscalationEvent.objects.get().escalated_to, None)
        self.assertIn("ESCALATED", self.kinds(self.officer))
        self.assertIn("ESCALATED_INFO", self.kinds(self.admin))

    # ---- level 2
    @override_settings(ESCALATION_LEVEL2_AFTER_HOURS=24)
    def test_level_two_after_the_configured_delay(self):
        c = self.complaint_with(hours_ago=30, sla_hours=24)
        run_sla_check(self.now)
        self.assertEqual(run_sla_check(self.now + timedelta(hours=23)).level2, 0)
        result = run_sla_check(self.now + timedelta(hours=25))
        self.assertEqual(result.level2, 1)
        c.refresh_from_db()
        self.assertEqual(c.escalation_level, 2)
        self.assertEqual(list(EscalationEvent.objects.values_list("level", flat=True)), [1, 2])
        self.assertIn("ESCALATED", self.kinds(self.admin))
        self.assertEqual(run_sla_check(self.now + timedelta(hours=50)).level2, 0)

    def test_resolved_complaints_are_not_escalated_further(self):
        c = self.complaint_with(hours_ago=30, sla_hours=24)
        run_sla_check(self.now)
        Complaint.objects.filter(pk=c.pk).update(status=S.RESOLVED)
        self.assertEqual(run_sla_check(self.now + timedelta(hours=40)).level2, 0)

    def test_unrouted_overdue_complaint_goes_straight_to_administrators(self):
        c = self.complaint_with(hours_ago=30, sla_hours=24, status=S.NEEDS_VERIFICATION, dept=None)
        result = run_sla_check(self.now)
        self.assertEqual(result.unrouted, 1)
        c.refresh_from_db()
        self.assertEqual(c.escalation_level, 2)
        self.assertIn("ESCALATED", self.kinds(self.admin))
        self.assertEqual(run_sla_check(self.now).unrouted, 0)

    def test_reopening_gives_a_fresh_clock_and_resets_escalation(self):
        c = self.complaint_with(hours_ago=30, sla_hours=24, status=S.RESOLVED)
        Complaint.objects.filter(pk=c.pk).update(escalation_level=2, resolved_at=timezone.now())
        c.refresh_from_db()
        reopen_complaint(c, citizen=self.citizen, reason="The problem came back after two days")
        c.refresh_from_db()
        self.assertEqual((c.escalation_level, c.sla_warned_at), (0, None))
        self.assertGreater(c.sla_deadline, timezone.now())

    def test_command_runs_and_reports(self):
        self.complaint_with(hours_ago=30, sla_hours=24)
        out = io.StringIO()
        call_command("check_sla", stdout=out)
        self.assertIn("escalated to department head: 1", out.getvalue())


class ManualEscalationTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.head = make_user("head@example.com", Role.OFFICER, department=self.elec, full_name="Gopal Hegde")
        OfficerProfile.objects.filter(user=self.head).update(is_department_head=True)
        self.admin = make_user("admin@example.com", Role.ADMIN)

    def test_officer_escalates_to_the_head_and_head_to_administrators(self):
        escalate_complaint(self.complaint, actor=self.officer, reason="Needs a second crew urgently")
        self.assertEqual(self.fresh().escalation_level, 1)
        self.assertEqual(EscalationEvent.objects.get().triggered_by, self.officer)
        self.assertTrue(Notification.objects.filter(recipient=self.head, kind="ESCALATED").exists())
        with self.assertRaisesMessage(WorkflowError, "already been escalated"):
            escalate_complaint(self.complaint, actor=self.officer, reason="Asking a second time again")
        escalate_complaint(self.complaint, actor=self.head, reason="Budget approval is needed here")
        self.assertEqual(self.fresh().escalation_level, 2)
        self.assertTrue(Notification.objects.filter(recipient=self.admin, kind="ESCALATED").exists())
        with self.assertRaises(WorkflowError):
            escalate_complaint(self.complaint, actor=self.head, reason="Nothing higher than administrators")

    def test_finished_complaints_cannot_be_escalated(self):
        done = self.make(status=S.CLOSED)
        with self.assertRaisesMessage(WorkflowError, "still being worked on"):
            escalate_complaint(done, actor=self.officer, reason="Too late to escalate this one")

    def test_through_the_page_and_filter_and_summary(self):
        self.as_officer()
        response = self.client.post(reverse("officer:escalate", args=[self.complaint.pk]), {"reason": "Needs a second crew urgently"}, follow=True)
        self.assertContains(response, "Complaint escalated")
        self.assertContains(response, "Escalated to Department Head")
        self.assertContains(response, "Needs a second crew urgently")
        dash = self.client.get(reverse("officer:dashboard"), {"escalation": "any"})
        self.assertEqual([c.pk for c in dash.context["complaints"]], [self.complaint.pk])
        self.assertEqual(dash.context["summary"]["escalated"], 1)
        self.assertContains(dash, "Dept. Head")
        self.assertEqual(self.client.get(reverse("officer:dashboard"), {"escalation": "2"}).context["complaints"].__len__(), 0)

    def test_other_department_and_roles_cannot_escalate(self):
        url = reverse("officer:escalate", args=[self.complaint.pk])
        self.client.force_login(self.water_officer)
        self.assertEqual(self.client.post(url, {"reason": "Not your department at all"}).status_code, 404)
        for user in (self.citizen, self.worker):
            self.client.force_login(user)
            self.assertEqual(self.client.post(url, {"reason": "Not allowed to do this one"}).status_code, 403)
        self.assertEqual(self.fresh().escalation_level, 0)

    def test_citizen_never_sees_escalation(self):
        escalate_complaint(self.complaint, actor=self.officer, reason="Needs a second crew urgently")
        self.as_citizen()
        page = self.client.get(reverse("complaints:detail", args=[self.complaint.pk])).content.decode()
        self.assertNotIn("scalat", page)
        self.assertFalse(Notification.objects.filter(recipient=self.citizen, kind__startswith="ESCALATED").exists())
