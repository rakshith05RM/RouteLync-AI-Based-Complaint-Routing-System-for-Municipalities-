from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from audit.models import AuditLog
from complaints.models import ComplaintStatus as S, RoutingCorrection, RoutingMethod
from complaints.selectors import complaints_visible_to
from complaints.services import WorkflowError, assign_worker, route_by_admin, start_work
from ml_engine.models import TrainingSample
from notifications.models import Notification

from .helpers import AdminTestCase


class VerificationQueueTests(AdminTestCase):
    def test_queue_lists_only_complaints_waiting_for_a_decision(self):
        waiting = self.waiting(title="Odd complaint about something")
        self.as_admin()
        page = self.client.get(reverse("adminpanel:queue"))
        self.assertEqual([c.pk for c in page.context["complaints"]], [waiting.pk])
        self.assertContains(page, "The model suggested")
        self.assertContains(page, "Electricity")
        self.assertNotContains(page, self.complaint.reference)

    def test_empty_queue_message(self):
        self.as_admin()
        self.assertContains(self.client.get(reverse("adminpanel:queue")), "The queue is empty")

    def test_confirming_the_models_suggestion(self):
        c = self.waiting()
        correction, note = route_by_admin(c, self.elec, actor=self.admin, add_to_training=False)
        c.refresh_from_db()
        self.assertEqual((c.status, c.department, c.routing_method), (S.PENDING, self.elec, RoutingMethod.MANUAL))
        self.assertEqual((correction.ai_was_correct, correction.was_unrouted, correction.corrected_by), (True, True, self.admin))
        self.assertTrue(Notification.objects.filter(recipient=self.officer, kind="NEW_COMPLAINT").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.citizen, kind="ROUTED").exists())

    def test_choosing_a_different_department_records_that_the_model_was_wrong(self):
        c = self.waiting()
        correction, _ = route_by_admin(c, self.water, actor=self.admin)
        c.refresh_from_db()
        self.assertEqual(c.department, self.water)
        self.assertEqual(c.predicted_department, self.elec)                      # the model's guess is preserved
        self.assertFalse(correction.ai_was_correct)

    def test_decision_becomes_a_verified_training_example(self):
        c = self.waiting(title="Streetlight flickers", description="The streetlight near the temple flickers all night and then goes off")
        correction, note = route_by_admin(c, self.elec, actor=self.admin, add_to_training=True)
        sample = TrainingSample.objects.get()
        self.assertEqual((sample.department, sample.is_verified, sample.complaint, sample.source), (self.elec, True, c, "VERIFIED_COMPLAINT"))
        self.assertIn("Streetlight flickers", sample.text)
        self.assertEqual(correction.training_sample, sample)
        self.assertEqual(note, "")

    def test_training_example_is_optional_and_never_duplicated(self):
        c = self.waiting(description="The streetlight near the temple flickers all night and then goes off")
        route_by_admin(c, self.elec, actor=self.admin, add_to_training=False)
        self.assertEqual(TrainingSample.objects.count(), 0)
        a = self.waiting(title="Same words", description="The streetlight near the temple flickers all night and then goes off again")
        route_by_admin(a, self.elec, actor=self.admin, add_to_training=True)
        b = self.make(title="Same words", description="The streetlight near the temple flickers all night and then goes off again", status=S.PENDING)
        _, note = route_by_admin(b, self.water, actor=self.admin, add_to_training=True)
        self.assertEqual(TrainingSample.objects.count(), 1)
        self.assertIn("already labelled Electricity", note)

    def test_through_the_page(self):
        c = self.waiting(description="Transformer near the market is humming and the lights flicker badly")
        self.as_admin()
        response = self.client.post(reverse("adminpanel:route", args=[c.pk]), {"department": self.elec.pk, "add_to_training": "on"}, follow=True)
        self.assertContains(response, "Department set.")
        c.refresh_from_db()
        self.assertEqual(c.status, S.PENDING)
        self.assertEqual(TrainingSample.objects.count(), 1)

    def test_invalid_choices_are_refused(self):
        c = self.waiting()
        self.as_admin()
        self.client.post(reverse("adminpanel:route", args=[c.pk]), {"department": ""})
        self.client.post(reverse("adminpanel:route", args=[c.pk]), {"department": 99999})
        self.assertEqual(self.client.get(reverse("adminpanel:queue")).context["complaints"].__len__(), 1)
        self.water.is_active = False
        self.water.save()
        self.client.post(reverse("adminpanel:route", args=[c.pk]), {"department": self.water.pk})
        c.refresh_from_db()
        self.assertEqual(c.status, S.NEEDS_VERIFICATION)

    def test_admin_can_reject_spam_from_the_queue(self):
        c = self.waiting()
        self.as_admin()
        self.client.post(reverse("adminpanel:reject", args=[c.pk]), {"reason": "This is advertising, not a complaint"})
        c.refresh_from_db()
        self.assertEqual(c.status, S.REJECTED)
        self.assertTrue(Notification.objects.filter(recipient=self.citizen, kind="REJECTED").exists())


class RerouteTests(AdminTestCase):
    def test_wrong_department_is_corrected_and_visibility_follows(self):
        route_by_admin(self.complaint, self.water, actor=self.admin)
        c = self.fresh()
        self.assertEqual((c.department, c.status, c.routing_method), (self.water, S.PENDING, RoutingMethod.MANUAL))
        self.assertNotIn(c, complaints_visible_to(self.officer))
        self.assertIn(c, complaints_visible_to(self.water_officer))
        self.assertTrue(Notification.objects.filter(recipient=self.water_officer, kind="NEW_COMPLAINT").exists())
        self.assertIn("moved the complaint from Electricity to Water Supply", c.status_history.last().note)
        self.assertFalse(RoutingCorrection.objects.get().was_unrouted)

    def test_assigned_work_is_released_when_the_department_changes(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        route_by_admin(self.complaint, self.water, actor=self.admin)
        c = self.fresh()
        self.assertEqual((c.status, c.department), (S.PENDING, self.water))
        self.assertNotIn(c, complaints_visible_to(self.worker))

    def test_cannot_move_work_that_has_started_or_finished(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        with self.assertRaisesMessage(WorkflowError, "cannot be moved"):
            route_by_admin(self.complaint, self.water, actor=self.admin)
        for status in (S.RESOLVED, S.CLOSED, S.REJECTED, S.SUBMITTED):
            other = self.make(status=status)
            with self.assertRaises(WorkflowError, msg=status):
                route_by_admin(other, self.water, actor=self.admin)

    def test_same_department_is_refused(self):
        with self.assertRaisesMessage(WorkflowError, "already in that department"):
            route_by_admin(self.complaint, self.elec, actor=self.admin)

    def test_detail_page_shows_the_routing_decision(self):
        route_by_admin(self.complaint, self.water, actor=self.admin)
        self.as_admin()
        page = self.client.get(reverse("adminpanel:complaint", args=[self.complaint.pk])).content.decode()
        self.assertIn("Routing decisions", page)
        self.assertIn("Moved to", page)
        self.assertIn("Water Supply", page)

    def test_decisions_are_audited(self):
        c = self.waiting()
        route_by_admin(c, self.elec, actor=self.admin)
        route_by_admin(self.complaint, self.water, actor=self.admin)
        actions = list(AuditLog.objects.filter(action__startswith="ROUTING").values_list("action", flat=True))
        self.assertCountEqual(actions, ["ROUTING_VERIFIED", "ROUTING_CORRECTED"])
        entry = AuditLog.objects.get(action="ROUTING_VERIFIED")
        self.assertEqual((entry.user, entry.target_type, entry.target_id), (self.admin, "Complaint", c.pk))
        self.assertTrue(entry.details["ai_was_correct"])
