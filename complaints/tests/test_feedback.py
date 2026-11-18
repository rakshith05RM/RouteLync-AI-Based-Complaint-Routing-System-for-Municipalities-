from django.db import IntegrityError, transaction
from django.urls import reverse

from accounts.tests.helpers import make_user
from complaints.models import ComplaintStatus as S, Feedback
from complaints.services import WorkflowError, assign_worker, complete_work, confirm_resolution, review_resolution, start_work, submit_feedback
from notifications.models import Notification

from .helpers import make_upload
from .workflow_helpers import WorkflowTestCase


class FeedbackTests(WorkflowTestCase):
    def resolve(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        complete_work(self.complaint, actor=self.worker, remarks="Replaced the lamp and tested it on site.", photo=make_upload())
        review_resolution(self.complaint, actor=self.officer, approve=True)

    def url(self):
        return reverse("complaints:feedback", args=[self.complaint.pk])

    def test_not_allowed_before_resolution(self):
        for status in (S.PENDING, S.IN_PROGRESS, S.REOPENED, S.REJECTED):
            c = self.make(status=status)
            with self.assertRaisesMessage(WorkflowError, "once the complaint has been resolved"):
                submit_feedback(c, citizen=self.citizen, rating=5)
        self.as_citizen()
        self.client.post(self.url(), {"rating": "5", "comment": "Great"})
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertNotIn("How did we do?", self.client.get(reverse("complaints:detail", args=[self.complaint.pk])).content.decode())

    def test_feedback_after_resolution_and_after_closing(self):
        self.resolve()
        submit_feedback(self.complaint, citizen=self.citizen, rating=4, comment="Quick and polite crew")
        fb = Feedback.objects.get()
        self.assertEqual((fb.rating, fb.comment), (4, "Quick and polite crew"))
        other = self.make(status=S.CLOSED)
        submit_feedback(other, citizen=self.citizen, rating=5)
        self.assertEqual(Feedback.objects.count(), 2)

    def test_only_once_and_only_by_the_owner(self):
        self.resolve()
        with self.assertRaisesMessage(WorkflowError, "only rate your own"):
            submit_feedback(self.complaint, citizen=make_user("x@example.com"), rating=5)
        submit_feedback(self.complaint, citizen=self.citizen, rating=5)
        with self.assertRaisesMessage(WorkflowError, "already given feedback"):
            submit_feedback(self.complaint, citizen=self.citizen, rating=1)
        self.assertEqual(Feedback.objects.get().rating, 5)

    def test_rating_range_enforced_in_code_and_database(self):
        self.resolve()
        for bad in (0, 6, -1):
            with self.assertRaises(WorkflowError):
                submit_feedback(self.complaint, citizen=self.citizen, rating=bad)
        for bad in (0, 6):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Feedback.objects.create(complaint=self.complaint, rating=bad)

    def test_through_the_page(self):
        self.resolve()
        self.as_citizen()
        page = self.client.get(reverse("complaints:detail", args=[self.complaint.pk])).content.decode()
        self.assertIn("How did we do?", page)
        response = self.client.post(self.url(), {"rating": "5", "comment": "Fixed within a day, thank you"}, follow=True)
        self.assertContains(response, "Thank you for your feedback")
        self.assertContains(response, "Your feedback")
        self.assertContains(response, "Fixed within a day, thank you")
        self.assertNotContains(response, "How did we do?")                           # the form is gone

    def test_invalid_form_input(self):
        self.resolve()
        self.as_citizen()
        for data in ({"rating": ""}, {"rating": "9"}, {"rating": "abc"}, {"rating": "3", "comment": "aaaaaaaaaa"}, {"rating": "3", "comment": "x" * 600}):
            self.client.post(self.url(), data)
        self.assertEqual(Feedback.objects.count(), 0)
        self.client.post(self.url(), {"rating": "3", "comment": ""})                   # a rating alone is fine
        self.assertEqual(Feedback.objects.get().comment, "")

    def test_others_cannot_rate(self):
        self.resolve()
        self.client.force_login(make_user("intruder@example.com"))
        self.assertEqual(self.client.post(self.url(), {"rating": "1"}).status_code, 404)
        self.client.force_login(self.officer)
        self.assertEqual(self.client.post(self.url(), {"rating": "1"}).status_code, 403)

    def test_officer_sees_feedback_and_low_ratings_alert_the_department(self):
        self.resolve()
        submit_feedback(self.complaint, citizen=self.citizen, rating=1, comment="Still dark at night")
        self.as_officer()
        page = self.client.get(reverse("officer:detail", args=[self.complaint.pk])).content.decode()
        self.assertIn("Citizen feedback", page)
        self.assertIn("Still dark at night", page)
        self.assertTrue(Notification.objects.filter(recipient=self.officer, kind="LOW_RATING").exists())

    def test_good_ratings_do_not_alert(self):
        self.resolve()
        submit_feedback(self.complaint, citizen=self.citizen, rating=5)
        self.assertFalse(Notification.objects.filter(kind="LOW_RATING").exists())
