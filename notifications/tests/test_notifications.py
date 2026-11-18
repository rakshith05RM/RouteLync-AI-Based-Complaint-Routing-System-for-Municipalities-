from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import ComplaintStatus as S
from complaints.services import (add_remark, assign_worker, complete_work, confirm_resolution, reject_complaint,
                                 reopen_complaint, review_resolution, start_work)
from complaints.tests.helpers import make_upload
from complaints.tests.workflow_helpers import WorkflowTestCase
from notifications.models import Notification
from notifications.services import notify

DONE = "Replaced the lamp and tested it on site."


class WhoIsToldTests(WorkflowTestCase):
    def messages(self, user):
        return list(Notification.objects.filter(recipient=user).order_by("id").values_list("kind", flat=True))

    def test_journey_notifies_the_right_people(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        self.assertEqual(self.messages(self.worker), ["JOB_ASSIGNED"])
        self.assertEqual(self.messages(self.citizen), ["WORKER_ASSIGNED"])
        start_work(self.complaint, actor=self.worker)
        self.assertEqual(self.messages(self.citizen)[-1], "IN_PROGRESS")
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload())
        self.assertEqual(self.messages(self.officer), ["AWAITING_VERIFICATION"])
        self.assertEqual(self.messages(self.water_officer), [])                 # other departments are not bothered
        review_resolution(self.complaint, actor=self.officer, approve=True)
        self.assertEqual(self.messages(self.citizen)[-1], "RESOLVED")
        reopen_complaint(self.complaint, citizen=self.citizen, reason="The light is dark again tonight")
        self.assertEqual(self.messages(self.officer)[-1], "REOPENED")

    def test_send_back_tells_the_worker(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload())
        review_resolution(self.complaint, actor=self.officer, approve=False, note="Still flickers")
        last = Notification.objects.filter(recipient=self.worker).latest("id")
        self.assertEqual(last.kind, "SENT_BACK")
        self.assertIn("Still flickers", last.message)

    def test_rejection_and_public_remarks_reach_the_citizen_but_internal_ones_do_not(self):
        add_remark(self.complaint, author=self.officer, text="Contractor was slow last time", visibility="INTERNAL")
        self.assertEqual(self.messages(self.citizen), [])
        add_remark(self.complaint, author=self.officer, text="Crew will visit tomorrow", visibility="PUBLIC")
        self.assertEqual(self.messages(self.citizen), ["UPDATE"])
        reject_complaint(self.complaint, actor=self.officer, reason="This is private property")
        self.assertEqual(self.messages(self.citizen)[-1], "REJECTED")

    def test_citizen_messages_use_plain_wording(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload())
        review_resolution(self.complaint, actor=self.officer, approve=True)
        for n in Notification.objects.filter(recipient=self.citizen):
            for hidden in ("Ravi", "priority", "confidence", "AI", "escalat", "model"):
                self.assertNotIn(hidden, n.message, n.message)

    def test_failed_action_leaves_no_notification_behind(self):
        from complaints.services import WorkflowError
        before = Notification.objects.count()
        with self.assertRaises(WorkflowError):
            assign_worker(self.complaint, self.water_worker, actor=self.officer)
        self.assertEqual(Notification.objects.count(), before)

    def test_inactive_users_are_not_notified(self):
        self.worker.is_active = False
        self.worker.save()
        self.assertIsNone(notify(self.worker, "Hello"))


class NotificationPageTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.a = Notification.objects.create(recipient=self.citizen, message="First", link=reverse("complaints:detail", args=[self.complaint.pk]))
        self.b = Notification.objects.create(recipient=self.citizen, message="Second", link="")
        self.other = Notification.objects.create(recipient=self.officer, message="Not yours")
        self.as_citizen()

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("notifications:list")).status_code, 302)

    def test_list_shows_only_my_notifications_newest_first(self):
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual([n.message for n in response.context["notifications"]], ["Second", "First"])
        self.assertNotContains(response, "Not yours")

    def test_bell_shows_the_unread_count_and_nothing_for_anonymous(self):
        self.assertContains(self.client.get(reverse("notifications:list")), 'aria-label="2 unread"')
        self.client.logout()
        self.assertNotContains(self.client.get("/"), "unread")

    def test_opening_marks_read_and_redirects_to_the_target(self):
        response = self.client.get(reverse("notifications:open", args=[self.a.pk]))
        self.assertRedirects(response, self.a.link)
        self.a.refresh_from_db()
        self.assertTrue(self.a.is_read)
        self.assertRedirects(self.client.get(reverse("notifications:open", args=[self.b.pk])), reverse("notifications:list"))

    def test_cannot_open_someone_elses_notification(self):
        self.assertEqual(self.client.get(reverse("notifications:open", args=[self.other.pk])).status_code, 404)
        self.other.refresh_from_db()
        self.assertFalse(self.other.is_read)

    def test_external_links_are_never_followed(self):
        for evil in ("https://evil.example/", "//evil.example/", "javascript:alert(1)"):
            n = Notification.objects.create(recipient=self.citizen, message="x", link=evil)
            self.assertRedirects(self.client.get(reverse("notifications:open", args=[n.pk])), reverse("notifications:list"))

    def test_mark_all_read_is_post_only_and_scoped(self):
        self.assertEqual(self.client.get(reverse("notifications:read_all")).status_code, 405)
        self.client.post(reverse("notifications:read_all"))
        self.assertEqual(Notification.objects.filter(recipient=self.citizen, is_read=False).count(), 0)
        self.other.refresh_from_db()
        self.assertFalse(self.other.is_read)

    def test_empty_state_and_pagination(self):
        self.client.force_login(make_user("new@example.com", Role.CITIZEN))
        self.assertContains(self.client.get(reverse("notifications:list")), "no notifications")
        user = make_user("busy@example.com", Role.CITIZEN)
        for i in range(25):
            Notification.objects.create(recipient=user, message=f"n{i}")
        self.client.force_login(user)
        self.assertEqual(len(self.client.get(reverse("notifications:list")).context["notifications"]), 20)
        self.assertEqual(len(self.client.get(reverse("notifications:list"), {"page": 2}).context["notifications"]), 5)
