from datetime import timedelta

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import (Complaint, ComplaintAssignment, ComplaintImage, ComplaintRemark, ComplaintStatus as S,
                               Resolution, ResolutionOutcome)
from complaints.presenters import citizen_tracker
from complaints.selectors import complaints_visible_to
from complaints.services import (WorkflowError, assign_worker, change_priority, complete_work, confirm_resolution,
                                 reject_complaint, reopen_complaint, review_resolution, start_work)
from departments.models import Priority

from .helpers import make_upload
from .workflow_helpers import WorkflowTestCase

DONE = "Replaced the burnt out lamp and tested it on site."


class LifecycleTests(WorkflowTestCase):
    def finish_work(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload())

    def resolve(self):
        self.finish_work()
        review_resolution(self.complaint, actor=self.officer, approve=True)

    def test_full_happy_path_in_order(self):
        self.finish_work()
        review_resolution(self.complaint, actor=self.officer, approve=True)
        self.assertEqual(self.fresh().status, S.RESOLVED)
        self.assertIsNotNone(self.complaint.resolved_at)
        confirm_resolution(self.complaint, citizen=self.citizen)
        c = self.fresh()
        self.assertEqual(c.status, S.CLOSED)
        self.assertIsNotNone(c.closed_at)
        steps = []                                      # collapse repeated entries ("work completed" is an event, not a change)
        for status in self.history():
            if not steps or steps[-1] != status:
                steps.append(status)
        self.assertEqual(steps[-4:], ["ASSIGNED_TO_WORKER", "IN_PROGRESS", "RESOLVED", "CLOSED"])
        res = Resolution.objects.get()
        self.assertEqual((res.outcome, res.reviewed_by), (ResolutionOutcome.VERIFIED, self.officer))
        self.assertIsNotNone(res.citizen_confirmed_at)
        self.assertFalse(ComplaintAssignment.objects.get().is_active)
        self.assertNotIn(self.complaint, complaints_visible_to(self.worker))     # closed work leaves the worker's list

    def test_officer_can_send_work_back_and_worker_tries_again(self):
        self.finish_work()
        with self.assertRaisesMessage(WorkflowError, "Explain what still needs"):
            review_resolution(self.complaint, actor=self.officer, approve=False, note="")
        review_resolution(self.complaint, actor=self.officer, approve=False, note="Light still flickers, check the wiring")
        c = self.fresh()
        self.assertEqual(c.status, S.IN_PROGRESS)
        self.assertEqual(Resolution.objects.get().outcome, ResolutionOutcome.SENT_BACK)
        self.assertIn("sent back", c.status_history.last().note)
        complete_work(self.complaint, actor=self.worker, remarks="Rewired the connector and checked it again", photo=make_upload())
        review_resolution(self.complaint, actor=self.officer, approve=True)
        self.assertEqual(self.fresh().status, S.RESOLVED)
        self.assertEqual(Resolution.objects.count(), 2)

    def test_review_requires_a_submitted_resolution(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        with self.assertRaisesMessage(WorkflowError, "no submitted resolution"):
            review_resolution(self.complaint, actor=self.officer, approve=True)

    def test_cannot_reassign_while_a_resolution_waits_for_review(self):
        self.finish_work()
        with self.assertRaisesMessage(WorkflowError, "Review the submitted resolution"):
            assign_worker(self.complaint, self.worker2, actor=self.officer)

    def test_reopen_returns_complaint_to_the_department(self):
        self.resolve()
        reopen_complaint(self.complaint, citizen=self.citizen, reason="The light went out again after one hour")
        c = self.fresh()
        self.assertEqual(c.status, S.REOPENED)
        self.assertIsNone(c.resolved_at)
        self.assertGreater(c.sla_deadline, timezone.now())                       # a fresh service clock
        res = Resolution.objects.get()
        self.assertEqual(res.outcome, ResolutionOutcome.DISPUTED)
        self.assertIn("went out again", res.dispute_reason)
        self.assertFalse(ComplaintAssignment.objects.get().is_active)
        remark = ComplaintRemark.objects.get()
        self.assertEqual((remark.author, remark.visibility), (self.citizen, "PUBLIC"))
        assign_worker(self.complaint, self.worker2, actor=self.officer)           # department review: assign again
        self.assertEqual(self.fresh().status, S.ASSIGNED_TO_WORKER)

    def test_reopen_rules(self):
        self.resolve()
        with self.assertRaisesMessage(WorkflowError, "only reopen your own"):
            reopen_complaint(self.complaint, citizen=make_user("x@example.com"), reason="not mine to reopen at all")
        Complaint.objects.filter(pk=self.complaint.pk).update(resolved_at=timezone.now() - timedelta(days=8))
        with self.assertRaisesMessage(WorkflowError, "within 7 days"):
            reopen_complaint(self.complaint, citizen=self.citizen, reason="too late now but still not fixed")
        with override_settings(REOPEN_WINDOW_DAYS=30):
            reopen_complaint(self.complaint, citizen=self.citizen, reason="inside the longer configured window")
        with self.assertRaisesMessage(WorkflowError, "Only a resolved complaint"):
            reopen_complaint(self.complaint, citizen=self.citizen, reason="already reopened once before")

    def test_closed_complaint_cannot_be_reopened_or_confirmed_again(self):
        self.resolve()
        confirm_resolution(self.complaint, citizen=self.citizen)
        with self.assertRaises(WorkflowError):
            reopen_complaint(self.complaint, citizen=self.citizen, reason="closed complaints stay closed")
        with self.assertRaises(WorkflowError):
            confirm_resolution(self.complaint, citizen=self.citizen)

    def test_confirm_only_by_the_owner_and_only_when_resolved(self):
        with self.assertRaises(WorkflowError):
            confirm_resolution(self.complaint, citizen=self.citizen)               # still PENDING
        self.resolve()
        with self.assertRaisesMessage(WorkflowError, "only confirm your own"):
            confirm_resolution(self.complaint, citizen=make_user("x@example.com"))

    def test_reject_before_work_starts(self):
        reject_complaint(self.complaint, actor=self.officer, reason="Duplicate of an existing complaint")
        c = self.fresh()
        self.assertEqual(c.status, S.REJECTED)
        remark = ComplaintRemark.objects.get()
        self.assertEqual(remark.visibility, "PUBLIC")
        self.assertIn("Duplicate of an existing complaint", remark.text)
        with self.assertRaises(WorkflowError):
            assign_worker(c, self.worker, actor=self.officer)
        other = self.make(status=S.IN_PROGRESS)
        with self.assertRaisesMessage(WorkflowError, "before work has been assigned"):
            reject_complaint(other, actor=self.officer, reason="Too late to reject this one")

    def test_priority_change_recalculates_the_deadline_and_is_recorded(self):
        before = self.complaint.sla_deadline
        change_priority(self.complaint, Priority.CRITICAL, actor=self.officer, reason="Children play near the pole")
        c = self.fresh()
        self.assertEqual(c.priority, Priority.CRITICAL)
        self.assertEqual((c.sla_deadline - c.created_at).total_seconds(), 4 * 3600)
        self.assertNotEqual(c.sla_deadline, before)
        self.assertIn("Changed by Meera Nair: Children play near the pole", c.priority_reason)
        self.assertIn("Medium to Critical", c.status_history.last().note)
        with self.assertRaises(WorkflowError):
            change_priority(c, Priority.CRITICAL, actor=self.officer, reason="same priority again")
        with self.assertRaises(WorkflowError):
            change_priority(c, "URGENT!!", actor=self.officer, reason="not a real priority")
        done = self.make(status=S.CLOSED)
        with self.assertRaises(WorkflowError):
            change_priority(done, Priority.LOW, actor=self.officer, reason="closed complaints are fixed")


class OfficerReviewViewTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload())
        self.as_officer()

    def detail(self):
        return self.client.get(reverse("officer:detail", args=[self.complaint.pk]))

    def test_detail_highlights_waiting_work_and_dashboard_flags_it(self):
        page = self.detail().content.decode()
        for expected in ("needs your verification", DONE, "Ravi Kumar", "Approve", "Send back"):
            self.assertIn(expected, page)
        dash = self.client.get(reverse("officer:dashboard"))
        self.assertContains(dash, "Awaiting verification")
        self.assertEqual(dash.context["summary"]["awaiting"], 1)
        filtered = self.client.get(reverse("officer:dashboard"), {"awaiting_verification": "on"})
        self.assertEqual([c.pk for c in filtered.context["complaints"]], [self.complaint.pk])

    def test_approve_through_the_page(self):
        response = self.client.post(reverse("officer:review", args=[self.complaint.pk]), {"decision": "approve", "note": ""}, follow=True)
        self.assertContains(response, "Resolution verified")
        self.assertEqual(self.fresh().status, S.RESOLVED)

    def test_send_back_needs_a_note(self):
        url = reverse("officer:review", args=[self.complaint.pk])
        response = self.client.post(url, {"decision": "send_back", "note": ""}, follow=True)
        self.assertContains(response, "Explain what still needs to be done")
        self.assertEqual(self.fresh().status, S.IN_PROGRESS)
        self.client.post(url, {"decision": "send_back", "note": "The pole base is still open"})
        self.assertEqual(Resolution.objects.get().outcome, ResolutionOutcome.SENT_BACK)

    def test_priority_remark_and_reject_endpoints(self):
        other = self.make(status=S.PENDING)
        self.client.post(reverse("officer:priority", args=[other.pk]), {"priority": "HIGH", "reason": "Near a school gate"})
        other.refresh_from_db()
        self.assertEqual(other.priority, "HIGH")
        self.client.post(reverse("officer:remark", args=[other.pk]), {"text": "Parts are on order", "visibility": "PUBLIC"})
        self.assertEqual(ComplaintRemark.objects.get(complaint=other).visibility, "PUBLIC")
        self.client.post(reverse("officer:remark", args=[other.pk]), {"text": "x", "visibility": "PUBLIC"})
        self.assertEqual(ComplaintRemark.objects.filter(complaint=other).count(), 1)             # too short: not saved
        self.client.post(reverse("officer:reject", args=[other.pk]), {"reason": "This is not a municipal matter"})
        other.refresh_from_db()
        self.assertEqual(other.status, S.REJECTED)

    def test_other_department_cannot_review(self):
        self.client.force_login(self.water_officer)
        self.assertEqual(self.client.post(reverse("officer:review", args=[self.complaint.pk]), {"decision": "approve"}).status_code, 404)
        self.assertEqual(self.fresh().status, S.IN_PROGRESS)


class CitizenViewTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.as_citizen()

    def page(self):
        return self.client.get(reverse("complaints:detail", args=[self.complaint.pk])).content.decode()

    def to_resolved(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload())
        return self

    def approve(self):
        review_resolution(self.complaint, actor=self.officer, approve=True)

    def test_tracker_follows_the_lifecycle(self):
        def states():
            self.complaint.refresh_from_db()
            return [s["state"] for s in citizen_tracker(Complaint.objects.prefetch_related("status_history").get(pk=self.complaint.pk))]
        from complaints.models import ComplaintStatusHistory
        for status in ("SUBMITTED", "AI_PROCESSING", "DEPARTMENT_ASSIGNED", "PENDING"):
            ComplaintStatusHistory.objects.create(complaint=self.complaint, to_status=status)
        self.assertEqual(states(), ["done", "done", "current", "todo", "todo", "todo"])
        assign_worker(self.complaint, self.worker, actor=self.officer)
        self.assertEqual(states(), ["done", "done", "done", "current", "todo", "todo"])
        start_work(self.complaint, actor=self.worker)
        self.assertEqual(states(), ["done", "done", "done", "done", "current", "todo"])
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload())
        self.approve()
        self.assertEqual(states(), ["done", "done", "done", "done", "done", "current"])
        confirm_resolution(self.complaint, citizen=self.citizen)
        self.assertEqual(states(), ["done"] * 6)

    def test_tracker_restarts_after_a_reopen_and_stops_at_rejection(self):
        self.to_resolved().approve()
        reopen_complaint(self.complaint, citizen=self.citizen, reason="The problem is back again today")
        steps = citizen_tracker(Complaint.objects.prefetch_related("status_history").get(pk=self.complaint.pk))
        self.assertEqual([s["state"] for s in steps][2:], ["current", "todo", "todo", "todo"])
        other = self.make(status=S.PENDING)
        reject_complaint(other, actor=self.officer, reason="Not a municipal responsibility at all")
        steps = citizen_tracker(Complaint.objects.prefetch_related("status_history").get(pk=other.pk))
        self.assertNotIn("current", [s["state"] for s in steps])

    def test_citizen_does_not_see_the_work_until_it_is_verified(self):
        self.to_resolved()
        page = self.page()
        self.assertNotIn(DONE, page)
        self.assertNotIn("Is the problem fixed?", page)
        res_image = ComplaintImage.objects.get(complaint=self.complaint)
        url = reverse("complaints:image", args=[self.complaint.pk, res_image.pk])
        self.assertEqual(self.client.get(url).status_code, 404)                    # photo hidden before verification
        self.approve()
        self.assertEqual(self.client.get(url).status_code, 200)
        page = self.page()
        for expected in (DONE, "Is the problem fixed?", "Yes, it is fixed", "No, it is not fixed", "Photo of the completed work"):
            self.assertIn(expected, page)

    def test_confirm_through_the_page(self):
        self.to_resolved().approve()
        response = self.client.post(reverse("complaints:confirm", args=[self.complaint.pk]), follow=True)
        self.assertContains(response, "now closed")
        self.assertEqual(self.fresh().status, S.CLOSED)
        self.assertContains(response, "How it was resolved")

    def test_reopen_through_the_page_needs_a_reason(self):
        self.to_resolved().approve()
        url = reverse("complaints:reopen", args=[self.complaint.pk])
        self.client.post(url, {"reason": "bad"})
        self.assertEqual(self.fresh().status, S.RESOLVED)
        response = self.client.post(url, {"reason": "The wire is still hanging loose near the gate"}, follow=True)
        self.assertContains(response, "has been reopened")
        self.assertEqual(self.fresh().status, S.REOPENED)
        self.assertContains(response, "Reopened by the citizen")                  # public update shown

    def test_reopen_button_disappears_after_the_window(self):
        self.to_resolved().approve()
        Complaint.objects.filter(pk=self.complaint.pk).update(resolved_at=timezone.now() - timedelta(days=9))
        page = self.page()
        self.assertIn("Yes, it is fixed", page)
        self.assertNotIn("No, it is not fixed", page)
        self.assertIn("period for reopening", page)

    def test_internal_remarks_and_internal_fields_stay_hidden(self):
        from complaints.services import add_remark
        add_remark(self.complaint, author=self.officer, text="Contractor was slow last time", visibility="INTERNAL")
        add_remark(self.complaint, author=self.officer, text="Crew will visit tomorrow morning", visibility="PUBLIC")
        page = self.page()
        self.assertIn("Crew will visit tomorrow morning", page)
        self.assertNotIn("Contractor was slow", page)
        for hidden in ("Awaiting officer", "priority", "SLA", "Ravi Kumar", "Officer note"):
            self.assertNotIn(hidden, page)

    def test_rejection_reason_is_shown_to_the_citizen(self):
        reject_complaint(self.complaint, actor=self.officer, reason="This is a private property matter")
        page = self.page()
        self.assertIn("Rejected", page)
        self.assertIn("This is a private property matter", page)

    def test_others_cannot_confirm_or_reopen(self):
        self.to_resolved().approve()
        self.client.force_login(make_user("intruder@example.com"))
        for name in ("confirm", "reopen"):
            self.assertEqual(self.client.post(reverse(f"complaints:{name}", args=[self.complaint.pk]), {"reason": "x" * 20}).status_code, 404)
        for user in (self.officer, self.worker):
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse("complaints:confirm", args=[self.complaint.pk])).status_code, 403)
        self.assertEqual(self.fresh().status, S.RESOLVED)
