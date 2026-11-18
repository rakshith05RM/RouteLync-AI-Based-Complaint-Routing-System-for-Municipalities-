"""The photo of the completed fix: mandatory before Resolved, stored on the complaint, visible to the citizen."""
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import Complaint, ComplaintImage, ComplaintStatus as S, Resolution, ResolutionOutcome
from complaints.services import (WorkflowError, assign_worker, complete_work, confirm_resolution, reopen_complaint,
                                 review_resolution, start_work)

from .helpers import make_upload
from .workflow_helpers import WorkflowTestCase

DONE = "Replaced the burnt out lamp and tested it on site."


class ResolutionPhotoTests(WorkflowTestCase):
    def work_done(self, name="fix.png"):
        assign_worker(self.complaint, self.worker, actor=self.officer) if not self.complaint.assignments.filter(ended_at__isnull=True).exists() else None
        if self.fresh().status == S.ASSIGNED_TO_WORKER:
            start_work(self.complaint, actor=self.worker)
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload(name))

    def url(self):
        return reverse("complaints:resolution_photo", args=[self.complaint.pk])

    def proof_url(self):
        return self.url()

    # ---- cannot be Resolved without the photo
    def test_officer_cannot_resolve_when_the_photo_is_missing(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        Resolution.objects.create(complaint=self.complaint, remarks=DONE, resolved_by=self.worker)      # work reported, but no photo on record
        with self.assertRaisesMessage(WorkflowError, "has no photo"):
            review_resolution(self.complaint, actor=self.officer, approve=True)
        c = self.fresh()
        self.assertEqual(c.status, S.IN_PROGRESS)
        self.assertEqual(Resolution.objects.get().outcome, ResolutionOutcome.PENDING_VERIFICATION)      # nothing half-done

    def test_no_code_path_can_set_resolved_without_a_photo(self):
        from complaints.services.transitions import transition_complaint
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        with self.assertRaisesMessage(WorkflowError, "photo of the completed work is required"):
            transition_complaint(self.complaint, S.RESOLVED, actor=self.officer)
        self.assertEqual(self.fresh().status, S.IN_PROGRESS)

    def test_the_officer_page_cannot_resolve_without_a_photo(self):
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        Resolution.objects.create(complaint=self.complaint, remarks=DONE, resolved_by=self.worker)
        self.as_officer()
        response = self.client.post(reverse("officer:review", args=[self.complaint.pk]), {"decision": "approve"}, follow=True)
        self.assertContains(response, "has no photo")
        self.assertEqual(self.fresh().status, S.IN_PROGRESS)

    def test_with_the_photo_the_complaint_can_be_resolved(self):
        self.work_done()
        review_resolution(self.complaint, actor=self.officer, approve=True)
        c = self.fresh()
        self.assertEqual(c.status, S.RESOLVED)
        self.assertTrue(c.resolution_photo)

    # ---- stored on the complaint, separate from the citizen's photo
    def test_the_proof_is_a_field_on_the_complaint_and_not_the_citizens_photo(self):
        original = ComplaintImage.objects.create(complaint=self.complaint, image=make_upload("citizen.png"), kind="EVIDENCE", uploaded_by=self.citizen)
        self.work_done()
        c = self.fresh()
        self.assertNotEqual(c.resolution_photo.name, original.image.name)
        self.assertEqual(c.resolution_photo.name, ComplaintImage.objects.get(kind="RESOLUTION").image.name)
        self.assertRegex(c.resolution_photo.name.rsplit("/", 1)[-1], r"^[0-9a-f]{32}\.png$")

    def test_a_new_photo_replaces_the_proof_after_work_is_sent_back(self):
        self.work_done("first.png")
        first = self.fresh().resolution_photo.name
        review_resolution(self.complaint, actor=self.officer, approve=False, note="The light still flickers")
        complete_work(self.complaint, actor=self.worker, remarks="Rewired the connector and tested again", photo=make_upload("second.png"))
        self.assertNotEqual(self.fresh().resolution_photo.name, first)
        self.assertEqual(ComplaintImage.objects.filter(kind="RESOLUTION").count(), 2)       # both attempts stay on record

    def test_reopening_clears_the_proof_so_a_new_one_is_needed(self):
        self.work_done()
        review_resolution(self.complaint, actor=self.officer, approve=True)
        reopen_complaint(self.complaint, citizen=self.citizen, reason="The light went out again after an hour")
        self.assertFalse(self.fresh().resolution_photo)
        assign_worker(self.complaint, self.worker2, actor=self.officer)
        start_work(self.complaint, actor=self.worker2)
        with self.assertRaises(WorkflowError):
            complete_work(self.complaint, actor=self.worker2, remarks=DONE)
        complete_work(self.complaint, actor=self.worker2, remarks=DONE, photo=make_upload("again.png"))
        review_resolution(self.complaint, actor=self.officer, approve=True)
        self.assertTrue(self.fresh().resolution_photo)


class CitizenSeesTheProofTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        assign_worker(self.complaint, self.worker, actor=self.officer)
        start_work(self.complaint, actor=self.worker)
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload("fix.png"))
        self.url = reverse("complaints:resolution_photo", args=[self.complaint.pk])
        self.detail = reverse("complaints:detail", args=[self.complaint.pk])

    def test_hidden_until_the_officer_has_verified_the_work(self):
        self.as_citizen()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertNotIn("proof-photo", self.client.get(self.detail).content.decode())
        review_resolution(self.complaint, actor=self.officer, approve=True)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_shown_with_the_progress_timeline_once_resolved(self):
        review_resolution(self.complaint, actor=self.officer, approve=True)
        self.as_citizen()
        page = self.client.get(self.detail).content.decode()
        progress = page.index("Progress")
        photo = page.index(self.url)
        question = page.index("Is the problem fixed?")
        self.assertLess(progress, photo)                                     # inside the Progress card, with the status steps
        self.assertLess(photo, question)
        self.assertIn("Photo of the completed work", page)
        self.assertIn("verified", page)
        self.assertEqual(page.count(self.url), 1)                            # shown once, not repeated

    def test_still_shown_after_the_citizen_closes_the_complaint(self):
        review_resolution(self.complaint, actor=self.officer, approve=True)
        confirm_resolution(self.complaint, citizen=self.citizen)
        self.as_citizen()
        self.assertIn(self.url, self.client.get(self.detail).content.decode())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_gone_again_after_a_reopen(self):
        review_resolution(self.complaint, actor=self.officer, approve=True)
        reopen_complaint(self.complaint, citizen=self.citizen, reason="The problem is back after two days")
        self.as_citizen()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertNotIn("proof-photo", self.client.get(self.detail).content.decode())

    def test_the_citizens_own_photo_is_shown_separately(self):
        ComplaintImage.objects.create(complaint=self.complaint, image=make_upload("mine.png"), kind="EVIDENCE", uploaded_by=self.citizen)
        review_resolution(self.complaint, actor=self.officer, approve=True)
        self.as_citizen()
        page = self.client.get(self.detail).content.decode()
        evidence = ComplaintImage.objects.get(kind="EVIDENCE")
        self.assertIn(reverse("complaints:image", args=[self.complaint.pk, evidence.pk]), page)
        self.assertIn(self.url, page)

    def test_served_as_an_image_with_safe_headers(self):
        review_resolution(self.complaint, actor=self.officer, approve=True)
        self.as_citizen()
        response = self.client.get(self.url)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        b"".join(response.streaming_content)

    def test_only_people_who_may_see_the_complaint_can_open_it(self):
        review_resolution(self.complaint, actor=self.officer, approve=True)
        allowed = {"officer": self.officer, "assigned worker": self.worker, "administrator": make_user("a@example.com", Role.ADMIN)}
        for label, user in allowed.items():
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 200, label)
        denied = {"another citizen": make_user("x@example.com", Role.CITIZEN), "another department's officer": self.water_officer,
                  "another worker": self.worker2}
        for label, user in denied.items():
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 404, label)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_staff_see_the_proof_on_their_pages(self):
        review_resolution(self.complaint, actor=self.officer, approve=True)
        self.as_officer()
        page = self.client.get(reverse("officer:detail", args=[self.complaint.pk])).content.decode()
        self.assertIn("Proof of the completed work", page)
        self.assertIn(self.url, page)
        self.client.force_login(make_user("a@example.com", Role.ADMIN))
        self.assertIn(self.url, self.client.get(reverse("adminpanel:complaint", args=[self.complaint.pk])).content.decode())

    def test_complaint_without_a_proof_has_no_photo_url(self):
        other = self.make(status=S.PENDING)
        self.as_officer()
        self.assertEqual(self.client.get(reverse("complaints:resolution_photo", args=[other.pk])).status_code, 404)
