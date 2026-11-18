import os
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests.helpers import make_user
from adminpanel import analytics
from complaints.models import Complaint, SubmissionAttempt
from complaints.services.attempts import discard_attempt, purge_old_attempts

from .helpers import make_upload
from .officer_helpers import OfficerTestCase

JUNK = "tttttttttrttttttttttttttt nsomtehing"
GOOD = "The streetlight near the junction has not been working for three days and the road is very dark at night."


class RejectedSubmissionTests(OfficerTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("complaints:new")
        self.client.force_login(self.citizen)

    def reject(self, **over):
        return self.client.post(self.url, self.payload(description=JUNK, **over))

    def test_a_rejected_description_stays_on_the_form_and_creates_no_complaint(self):
        response = self.reject()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not submitted: Not a municipal issue")
        self.assertContains(response, "No complaint was created")
        self.assertNotContains(response, "submitted successfully")
        self.assertEqual(Complaint.objects.count(), 0)
        self.assertEqual(SubmissionAttempt.objects.count(), 1)

    def test_what_the_citizen_typed_and_the_photo_are_kept(self):
        self.reject(title="Light is out", landmark="Near Metro", street="4th Main Road")
        a = SubmissionAttempt.objects.get()
        self.assertEqual((a.title, a.description, a.street, a.landmark, a.ward), ("Light is out", JUNK, "4th Main Road", "Near Metro", self.ward))
        self.assertEqual((a.reason_code, a.reason_label), ("NONSENSE", "Not a municipal issue"))
        self.assertTrue(a.image and os.path.exists(a.image.path))
        page = self.client.get(self.url, {"attempt": a.pk}).content.decode()
        self.assertIn(JUNK, page)
        self.assertIn("Light is out", page)
        self.assertIn("Your photo from the previous try is kept", page)
        self.assertNotRegex(page, r'<input type="file" name="image"[^>]*required')     # no need to choose the photo again

    def test_correcting_the_description_submits_without_re_uploading_and_removes_the_draft(self):
        self.reject()
        a = SubmissionAttempt.objects.get()
        path = a.image.path
        response = self.client.post(self.url, self.payload(description=GOOD, image=None, attempt=a.pk))
        c = Complaint.objects.get()
        self.assertRedirects(response, reverse("complaints:detail", args=[c.pk]))
        self.assertEqual(c.images.count(), 1)                                   # the kept photo became the complaint's photo
        self.assertEqual(SubmissionAttempt.objects.count(), 0)
        self.assertFalse(os.path.exists(path))

    def test_a_new_photo_replaces_the_kept_one(self):
        self.reject()
        a = SubmissionAttempt.objects.get()
        self.client.post(self.url, self.payload(description=GOOD, attempt=a.pk, image=make_upload("new.png", size=(60, 40))))
        self.assertEqual(Complaint.objects.get().images.count(), 1)

    def test_repeated_rejections_reuse_one_draft_and_one_success_makes_one_complaint(self):
        self.reject()
        a = SubmissionAttempt.objects.get()
        for _ in range(3):
            self.client.post(self.url, self.payload(description="I am testing this website", attempt=a.pk, image=None))
        self.assertEqual(SubmissionAttempt.objects.count(), 1)
        self.client.post(self.url, self.payload(description=GOOD, attempt=a.pk, image=None))
        self.assertEqual((Complaint.objects.count(), SubmissionAttempt.objects.count()), (1, 0))

    def test_sending_the_same_form_twice_creates_one_complaint(self):
        token = "a" * 32
        first = self.client.post(self.url, self.payload(submission_token=token))
        second = self.client.post(self.url, self.payload(submission_token=token), follow=True)
        self.assertEqual(Complaint.objects.count(), 1)
        self.assertContains(second, "was already submitted")
        self.assertEqual(first["Location"], second.redirect_chain[0][0])

    def test_other_errors_do_not_create_drafts(self):
        self.client.post(self.url, self.payload(ward=""))                       # missing ward, good description
        self.client.post(self.url, self.payload(street=""))
        self.client.post(self.url, self.payload(image=None))
        self.assertEqual(SubmissionAttempt.objects.count(), 0)

    def test_a_valid_complaint_leaves_no_draft(self):
        self.client.post(self.url, self.payload())
        self.assertEqual((Complaint.objects.count(), SubmissionAttempt.objects.count()), (1, 0))

    def test_a_bad_photo_is_not_kept(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.post(self.url, self.payload(description=JUNK, image=SimpleUploadedFile("a.jpg", b"not an image", content_type="image/jpeg")))
        a = SubmissionAttempt.objects.get()
        self.assertFalse(a.image)

    @override_settings(MAX_ATTEMPTS_PER_DAY=2)
    def test_the_number_of_drafts_per_day_is_limited_but_the_error_is_still_shown(self):
        for _ in range(3):
            response = self.reject()
            self.assertContains(response, "Not submitted")
        self.assertEqual(SubmissionAttempt.objects.count(), 2)

    def test_only_the_newest_twenty_drafts_are_kept(self):
        with override_settings(MAX_ATTEMPTS_PER_DAY=100):
            for _ in range(23):
                self.reject()
        self.assertEqual(SubmissionAttempt.objects.count(), 20)

    def test_someone_elses_draft_cannot_be_loaded(self):
        other = make_user("other@example.com", Role.CITIZEN)
        theirs = SubmissionAttempt.objects.create(citizen=other, title="Private title", description="private words here", reason_code="UNCLEAR", reason_label="x", message="m")
        page = self.client.get(self.url, {"attempt": theirs.pk}).content.decode()
        self.assertNotIn("Private title", page)
        self.client.post(self.url, self.payload(attempt=theirs.pk))
        self.assertTrue(SubmissionAttempt.objects.filter(pk=theirs.pk).exists())          # not consumed by someone else's submission


class DashboardTests(OfficerTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.citizen)
        self.client.post(reverse("complaints:new"), self.payload(description="Please help me correct the name on my ration card as soon as possible", title="Ration card matter"))
        self.attempt = SubmissionAttempt.objects.get()

    def test_the_citizen_sees_what_was_not_submitted_and_why(self):
        page = self.client.get(reverse("complaints:my_complaints")).content.decode()
        for expected in ("Not submitted", "no complaint was created", "Ration card matter", "Outside supported categories",
                         "outside the currently supported complaint categories", "Edit and submit again", "Remove"):
            self.assertIn(expected, page)
        self.assertIn(f"?attempt={self.attempt.pk}", page)

    def test_a_draft_is_not_a_complaint(self):
        page = self.client.get(reverse("complaints:my_complaints"))
        self.assertEqual(len(page.context["complaints"]), 0)
        self.assertNotContains(page, "RL-")
        self.assertContains(page, "not reported any problems")                  # the real-complaints list is still empty

    def test_drafts_never_appear_in_staff_views_or_statistics(self):
        self.assertEqual(Complaint.objects.count(), 0)
        self.assertEqual(analytics.summary_counts()["total"], 0)
        self.client.force_login(self.officer)
        self.assertEqual(len(self.client.get(reverse("officer:dashboard")).context["complaints"]), 0)
        self.client.force_login(make_user("a@example.com", Role.ADMIN))
        self.assertEqual(len(self.client.get(reverse("adminpanel:complaints")).context["complaints"]), 0)
        self.assertNotContains(self.client.get(reverse("adminpanel:dashboard")), "Ration card matter")

    def test_each_citizen_sees_only_their_own_drafts(self):
        self.client.force_login(make_user("other@example.com", Role.CITIZEN))
        self.assertNotContains(self.client.get(reverse("complaints:my_complaints")), "Ration card matter")

    def test_discarding_a_draft(self):
        path = self.attempt.image.path
        url = reverse("complaints:attempt_discard", args=[self.attempt.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, follow=True)
        self.assertContains(response, "draft was removed")
        self.assertFalse(SubmissionAttempt.objects.exists())
        self.assertFalse(os.path.exists(path))

    def test_only_the_owner_can_discard(self):
        self.client.force_login(make_user("other@example.com", Role.CITIZEN))
        self.assertEqual(self.client.post(reverse("complaints:attempt_discard", args=[self.attempt.pk])).status_code, 404)
        self.client.force_login(self.officer)
        self.assertEqual(self.client.post(reverse("complaints:attempt_discard", args=[self.attempt.pk])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("complaints:attempt_discard", args=[self.attempt.pk])).status_code, 302)
        self.assertTrue(SubmissionAttempt.objects.exists())

    def test_old_drafts_are_purged_with_their_photos(self):
        path = self.attempt.image.path
        SubmissionAttempt.objects.filter(pk=self.attempt.pk).update(updated_at=timezone.now() - timedelta(days=15))
        fresh = SubmissionAttempt.objects.create(citizen=self.citizen, reason_code="UNCLEAR", reason_label="x", message="m")
        out = StringIO()
        call_command("purge_old_attempts", stdout=out)
        self.assertIn("Removed 1", out.getvalue())
        self.assertEqual(list(SubmissionAttempt.objects.values_list("pk", flat=True)), [fresh.pk])
        self.assertFalse(os.path.exists(path))
