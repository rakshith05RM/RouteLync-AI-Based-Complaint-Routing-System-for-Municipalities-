from django.db import IntegrityError, transaction
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import ComplaintAssignment, ComplaintStatus as S
from complaints.selectors import complaints_visible_to
from complaints.services import WorkflowError, assign_worker, unassign_worker
from departments.models import FieldWorkerProfile

from .workflow_helpers import WorkflowTestCase


class AssignWorkerServiceTests(WorkflowTestCase):
    def test_assign_sets_status_assignment_and_history(self):
        assign_worker(self.complaint, self.worker, actor=self.officer, note="Take a ladder")
        c = self.fresh()
        self.assertEqual(c.status, S.ASSIGNED_TO_WORKER)
        a = ComplaintAssignment.objects.get()
        self.assertEqual((a.assigned_to, a.assigned_by, a.is_active, a.note), (self.worker, self.officer, True, "Take a ladder"))
        self.assertEqual(self.history()[-1], "ASSIGNED_TO_WORKER")
        self.assertIn("Ravi Kumar", c.status_history.last().note)

    def test_worker_only_sees_the_complaint_once_assigned(self):
        self.assertNotIn(self.complaint, complaints_visible_to(self.worker))
        assign_worker(self.complaint, self.worker, actor=self.officer)
        self.assertIn(self.complaint, complaints_visible_to(self.worker))
        self.assertNotIn(self.complaint, complaints_visible_to(self.worker2))

    def test_rules_for_who_can_be_assigned(self):
        with self.assertRaisesMessage(WorkflowError, "different department"):
            assign_worker(self.complaint, self.water_worker, actor=self.officer)
        with self.assertRaisesMessage(WorkflowError, "not a field worker"):
            assign_worker(self.complaint, self.citizen, actor=self.officer)
        profile = FieldWorkerProfile.objects.get(user=self.worker)
        profile.is_available = False
        profile.save()
        with self.assertRaisesMessage(WorkflowError, "not available"):
            assign_worker(self.complaint, self.worker, actor=self.officer)
        self.assertEqual(self.fresh().status, S.PENDING)

    def test_only_work_in_progress_states_can_be_assigned(self):
        for status in (S.SUBMITTED, S.NEEDS_VERIFICATION, S.RESOLVED, S.CLOSED, S.REJECTED):
            c = self.make(status=status)
            with self.assertRaises(WorkflowError, msg=status):
                assign_worker(c, self.worker, actor=self.officer)

    def test_reassign_ends_previous_assignment_and_keeps_one_active(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        assign_worker(self.complaint, self.worker2, actor=self.officer)
        rows = ComplaintAssignment.objects.order_by("id")
        self.assertEqual([(r.assigned_to.full_name, r.is_active) for r in rows], [("Ravi Kumar", False), ("Manoj Shetty", True)])
        self.assertEqual(self.fresh().status, S.ASSIGNED_TO_WORKER)
        self.assertIn("Reassigned from Ravi Kumar to Manoj Shetty", self.complaint.status_history.last().note)
        self.assertNotIn(self.complaint, complaints_visible_to(self.worker))     # the previous worker loses access
        self.assertIn(self.complaint, complaints_visible_to(self.worker2))

    def test_assigning_the_same_worker_again_is_refused(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        with self.assertRaisesMessage(WorkflowError, "already assigned"):
            assign_worker(self.complaint, self.worker, actor=self.officer)

    def test_database_allows_only_one_active_assignment_per_complaint(self):
        ComplaintAssignment.objects.create(complaint=self.complaint, assigned_to=self.worker, assigned_by=self.officer)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ComplaintAssignment.objects.create(complaint=self.complaint, assigned_to=self.worker2, assigned_by=self.officer)
        ended = ComplaintAssignment.objects.get()
        ended.ended_at = ended.assigned_at
        ended.save()
        ComplaintAssignment.objects.create(complaint=self.complaint, assigned_to=self.worker2, assigned_by=self.officer)

    def test_unassign_returns_complaint_to_queue(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        unassign_worker(self.complaint, actor=self.officer)
        self.assertEqual(self.fresh().status, S.PENDING)
        self.assertFalse(ComplaintAssignment.objects.get().is_active)
        self.assertNotIn(self.complaint, complaints_visible_to(self.worker))
        with self.assertRaises(WorkflowError):
            unassign_worker(self.complaint, actor=self.officer)


class AssignViewTests(WorkflowTestCase):
    def assign_url(self, c=None):
        return reverse("officer:assign", args=[(c or self.complaint).pk])

    def test_officer_assigns_through_the_page(self):
        self.as_officer()
        response = self.client.post(self.assign_url(), {"worker": self.worker.pk, "note": ""}, follow=True)
        self.assertContains(response, "Field worker assigned")
        self.assertEqual(self.fresh().status, S.ASSIGNED_TO_WORKER)
        self.assertContains(response, "Ravi Kumar")

    def test_the_picker_lists_only_available_workers_of_this_department(self):
        self.as_officer()
        page = self.client.get(reverse("officer:detail", args=[self.complaint.pk])).content.decode()
        self.assertIn("Ravi Kumar (0 open)", page)
        self.assertIn("Manoj Shetty", page)
        self.assertNotIn("Lakshmi Devi", page)

    def test_worker_from_another_department_cannot_be_posted_directly(self):
        self.as_officer()
        response = self.client.post(self.assign_url(), {"worker": self.water_worker.pk}, follow=True)
        self.assertEqual(self.fresh().status, S.PENDING)
        self.assertContains(response, "Select a valid choice")

    def test_officer_of_another_department_gets_404(self):
        self.client.force_login(self.water_officer)
        self.assertEqual(self.client.post(self.assign_url(), {"worker": self.water_worker.pk}).status_code, 404)
        self.assertEqual(self.fresh().status, S.PENDING)

    def test_other_roles_and_anonymous_cannot_assign(self):
        for user in (self.citizen, self.worker, make_user("a@example.com", Role.ADMIN)):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.assign_url(), {"worker": self.worker.pk}).status_code, 403, user.role)
        self.client.logout()
        self.assertEqual(self.client.post(self.assign_url(), {"worker": self.worker.pk}).status_code, 302)
        self.assertEqual(self.fresh().status, S.PENDING)

    def test_get_is_not_allowed_and_csrf_is_enforced(self):
        from django.test import Client
        self.as_officer()
        self.assertEqual(self.client.get(self.assign_url()).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.officer)
        self.assertEqual(strict.post(self.assign_url(), {"worker": self.worker.pk}).status_code, 403)

    def test_assignment_filter_on_the_dashboard(self):
        mine = self.make(title="Assigned one", status=S.PENDING)
        assign_worker(mine, self.worker, actor=self.officer)
        self.as_officer()
        def refs(**params):
            return {c.reference for c in self.client.get(reverse("officer:dashboard"), params).context["complaints"]}
        self.assertEqual(refs(assigned_to=self.worker.pk), {mine.reference})
        self.assertEqual(refs(assigned_to=self.worker2.pk), set())
        self.assertEqual(refs(assigned_to="none"), {self.complaint.reference})
        # a worker of another department is not a valid choice here: the filter is ignored and a warning is shown
        self.assertEqual(len(refs(assigned_to=self.water_worker.pk)), 2)
        self.assertContains(self.client.get(reverse("officer:dashboard"), {"assigned_to": self.water_worker.pk}), "Some filters were ignored")
        self.assertEqual(len(refs()), 2)

    def test_dashboard_shows_the_assigned_worker(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        self.as_officer()
        page = self.client.get(reverse("officer:dashboard")).content.decode()
        self.assertIn("Ravi Kumar", page)

    def test_return_to_queue_through_the_page(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        self.as_officer()
        self.client.post(reverse("officer:unassign", args=[self.complaint.pk]))
        self.assertEqual(self.fresh().status, S.PENDING)
