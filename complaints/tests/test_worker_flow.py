from django.test import override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import ComplaintImage, ComplaintRemark, ComplaintStatus as S, ImageKind, Resolution, ResolutionOutcome
from complaints.services import WorkflowError, assign_worker, complete_work, start_work

from .helpers import make_upload
from .workflow_helpers import WorkflowTestCase

DONE = "Replaced the burnt out lamp and tested it on site."


class WorkerAccessTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        assign_worker(self.complaint, self.worker, actor=self.officer)

    def test_dashboard_lists_only_my_assigned_work(self):
        other = self.make(title="Someone else's job", status=S.PENDING)
        assign_worker(other, self.worker2, actor=self.officer)
        self.make(title="Not assigned to anybody")
        self.as_worker()
        response = self.client.get(reverse("worker:dashboard"))
        self.assertEqual([c.pk for c in response.context["complaints"]], [self.complaint.pk])
        self.assertNotContains(response, "Someone else's job")

    def test_detail_is_404_for_work_not_assigned_to_me(self):
        self.as_worker(self.worker2)
        self.assertEqual(self.client.get(reverse("worker:detail", args=[self.complaint.pk])).status_code, 404)
        self.as_worker(self.water_worker)
        self.assertEqual(self.client.get(reverse("worker:detail", args=[self.complaint.pk])).status_code, 404)

    def test_only_field_workers_reach_worker_pages(self):
        for user in (self.citizen, self.officer, make_user("a@example.com", Role.ADMIN)):
            self.client.force_login(user)
            for url in (reverse("worker:dashboard"), reverse("worker:detail", args=[self.complaint.pk])):
                self.assertEqual(self.client.get(url).status_code, 403, f"{user.role} {url}")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("worker:dashboard")).status_code, 302)

    def test_worker_cannot_reach_officer_or_admin_pages(self):
        self.as_worker()
        self.assertEqual(self.client.get(reverse("officer:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("officer:detail", args=[self.complaint.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("officer:assign", args=[self.complaint.pk]), {"worker": self.worker.pk}).status_code, 403)

    def test_detail_shows_location_deadline_contact_but_not_ai_details(self):
        self.as_worker()
        page = self.client.get(reverse("worker:detail", args=[self.complaint.pk])).content.decode()
        for expected in ("4th Main Road", "Jayanagar, Ward 154", self.citizen.full_name, "Start work"):
            self.assertIn(expected, page)
        for hidden in ("AI routing", "confidence", self.citizen.email, "Predicted"):
            self.assertNotIn(hidden, page)

    def test_tabs_separate_todo_review_and_done(self):
        self.as_worker()
        start_work(self.complaint, actor=self.worker)
        counts = {k: n for k, _, n in self.client.get(reverse("worker:dashboard")).context["tabs"]}
        self.assertEqual(counts, {"todo": 1, "review": 0, "done": 0})
        complete_work(self.complaint, actor=self.worker, remarks=DONE, photo=make_upload())
        counts = {k: n for k, _, n in self.client.get(reverse("worker:dashboard")).context["tabs"]}
        self.assertEqual(counts, {"todo": 0, "review": 1, "done": 0})
        self.assertEqual(len(self.client.get(reverse("worker:dashboard"), {"show": "review"}).context["complaints"]), 1)


class WorkerActionTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        assign_worker(self.complaint, self.worker, actor=self.officer)
        self.as_worker()

    def url(self, name):
        return reverse(f"worker:{name}", args=[self.complaint.pk])

    def test_start_work(self):
        self.client.post(self.url("start"))
        self.assertEqual(self.fresh().status, S.IN_PROGRESS)
        self.assertEqual(self.history()[-1], "IN_PROGRESS")
        response = self.client.post(self.url("start"), follow=True)               # twice -> friendly refusal
        self.assertContains(response, "not available while the complaint is")

    def test_another_worker_cannot_start_it(self):
        self.as_worker(self.worker2)
        self.assertEqual(self.client.post(self.url("start")).status_code, 404)
        self.assertEqual(self.fresh().status, S.ASSIGNED_TO_WORKER)

    def test_cannot_complete_before_starting(self):
        response = self.client.post(self.url("complete"), {"remarks": DONE, "photo": make_upload("early.png")}, follow=True)
        self.assertContains(response, "Start the work before")
        self.assertEqual(Resolution.objects.count(), 0)

    def test_complete_work_creates_pending_resolution_with_photo(self):
        self.client.post(self.url("start"))
        response = self.client.post(self.url("complete"), {"remarks": DONE, "photo": make_upload("after.png")}, follow=True)
        self.assertContains(response, "Marked as completed")
        c = self.fresh()
        self.assertEqual(c.status, S.IN_PROGRESS)                                  # still in progress until the officer verifies
        res = Resolution.objects.get()
        self.assertEqual((res.outcome, res.resolved_by, res.remarks), (ResolutionOutcome.PENDING_VERIFICATION, self.worker, DONE))
        image = ComplaintImage.objects.get(complaint=c)
        self.assertEqual((image.kind, image.resolution, image.uploaded_by), (ImageKind.RESOLUTION, res, self.worker))
        self.assertRegex(image.image.name.rsplit("/", 1)[-1], r"^[0-9a-f]{32}\.png$")
        self.assertContains(response, "waiting for verification")
        self.assertNotContains(response, "Submit for verification")                # form is gone while waiting

    def test_completing_twice_while_waiting_is_refused(self):
        self.client.post(self.url("start"))
        self.client.post(self.url("complete"), {"remarks": DONE, "photo": make_upload("a.png")})
        self.client.post(self.url("complete"), {"remarks": DONE, "photo": make_upload("b.png")}, follow=True)
        self.assertEqual(Resolution.objects.count(), 1)

    def test_remarks_are_validated(self):
        self.client.post(self.url("start"))
        for bad in ("", "ok", "test", "aaaaaaaaaaaa"):
            self.client.post(self.url("complete"), {"remarks": bad})
        self.assertEqual(Resolution.objects.count(), 0)

    def test_invalid_photo_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.post(self.url("start"))
        fake = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        response = self.client.post(self.url("complete"), {"remarks": DONE, "photo": fake}, follow=True)
        self.assertContains(response, "not a valid image")
        self.assertEqual(Resolution.objects.count(), 0)

    def test_a_photo_of_the_finished_work_is_always_required(self):
        self.client.post(self.url("start"))
        response = self.client.post(self.url("complete"), {"remarks": DONE}, follow=True)
        self.assertContains(response, "Attach a photo of the finished work")
        self.assertEqual(Resolution.objects.count(), 0)
        self.assertEqual(self.fresh().resolution_photo.name, "")
        with self.assertRaisesMessage(WorkflowError, "attach a photo"):
            complete_work(self.complaint, actor=self.worker, remarks=DONE)            # the service refuses too, not only the form
        self.assertContains(self.client.get(self.url("detail")), 'name="photo" id="id_photo"')
        self.assertRegex(self.client.get(self.url("detail")).content.decode(), r'<input type="file" name="photo"[^>]*required')

    def test_the_photo_is_stored_on_the_complaint_separately_from_the_citizens_photo(self):
        from complaints.models import ComplaintImage
        ComplaintImage.objects.create(complaint=self.complaint, image=make_upload("citizen.png"), kind="EVIDENCE", uploaded_by=self.citizen)
        self.client.post(self.url("start"))
        self.client.post(self.url("complete"), {"remarks": DONE, "photo": make_upload("fix.png")})
        c = self.fresh()
        proof = ComplaintImage.objects.get(complaint=c, kind="RESOLUTION")
        self.assertTrue(c.resolution_photo)
        self.assertEqual(c.resolution_photo.name, proof.image.name)                 # the proof of the fix
        self.assertNotEqual(c.resolution_photo.name, ComplaintImage.objects.get(kind="EVIDENCE").image.name)   # not the citizen's photo

    def test_field_remark_is_staff_only(self):
        self.client.post(self.url("remark"), {"text": "Gate was locked, will return after lunch", "visibility": "PUBLIC"})
        remark = ComplaintRemark.objects.get()
        self.assertEqual((remark.author, remark.visibility), (self.worker, "INTERNAL"))    # workers cannot publish

    def test_service_level_guards(self):
        with self.assertRaisesMessage(WorkflowError, "not assigned to you"):
            start_work(self.complaint, actor=self.worker2)
