import os
from unittest import mock

from django.conf import settings
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from complaints.models import (Complaint, ComplaintImage, ComplaintLocation, ComplaintStatus,
                               ComplaintStatusHistory)

from .helpers import ComplaintTestCase, make_upload


class SubmissionTests(ComplaintTestCase):
    url = reverse("complaints:new")

    def setUp(self):
        super().setUp()
        self.client.force_login(self.citizen)

    def test_form_page_renders_with_ward_data_attributes(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Use my current location")
        self.assertContains(response, f'data-area="{self.area.pk}"')
        self.assertContains(response, 'data-tile-url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/')

    def test_valid_submission_creates_all_records(self):
        data = self.payload(latitude="12.925012", longitude="77.593800", image=make_upload("pole.png"))
        response = self.client.post(self.url, data)
        complaint = Complaint.objects.get()
        self.assertRedirects(response, reverse("complaints:detail", args=[complaint.pk]))
        self.assertEqual(complaint.citizen, self.citizen)
        # no ML model is active in this test, so routing falls back to human verification
        self.assertEqual(complaint.status, ComplaintStatus.NEEDS_VERIFICATION)
        self.assertIsNone(complaint.department)
        loc = complaint.location
        self.assertEqual((loc.ward, loc.street, loc.landmark), (self.ward, "4th Main Road", "Near Metro"))
        self.assertTrue(loc.has_gps)
        self.assertEqual(complaint.images.count(), 1)
        history = list(complaint.status_history.all())
        self.assertEqual([h.to_status for h in history][0], ComplaintStatus.SUBMITTED)
        self.assertEqual(history[0].changed_by, self.citizen)

    @override_settings(NOTIFY_EMAIL_ENABLED=True, NOTIFY_WHATSAPP_ENABLED=False, NOTIFY_ASYNC=False,
                       SITE_URL="https://city.example")
    def test_submitted_complaint_emails_the_citizen_a_tracking_link(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, self.payload(image=make_upload("pole.png")))

        complaint = Complaint.objects.get()
        citizen_messages = [
            message for message in mail.outbox
            if self.citizen.email in message.to and "submitted successfully" in message.body
        ]
        self.assertEqual(len(citizen_messages), 1)
        expected_url = f"https://city.example{reverse('complaints:detail', args=[complaint.pk])}"
        self.assertIn(expected_url, citizen_messages[0].body)
        self.assertIn(f'href="{expected_url}"', citizen_messages[0].alternatives[0][0])

    def test_typed_ward_number_is_saved_for_the_selected_area(self):
        response = self.client.post(self.url, self.payload(ward=999))
        complaint = Complaint.objects.get()
        self.assertRedirects(response, reverse("complaints:detail", args=[complaint.pk]))
        self.assertEqual(complaint.location.ward.number, 999)
        self.assertEqual(complaint.location.ward.area, self.area)

    def test_a_complaint_without_a_location_is_refused(self):
        response = self.client.post(self.url, self.payload(latitude="", longitude=""))
        self.assertContains(response, "choose the location of the problem")
        self.assertFalse(Complaint.objects.exists())

    def test_invalid_submission_saves_nothing_and_shows_errors(self):
        response = self.client.post(self.url, self.payload(description="test", street=""))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "too short")
        self.assertFalse(Complaint.objects.exists())

    def test_typed_ward_number_is_preserved_in_a_rejected_draft(self):
        self.client.post(self.url, self.payload(description="test", ward=999))
        attempt = self.citizen.submission_attempts.get()
        self.assertEqual(attempt.ward_text, "999")
        response = self.client.get(self.url, {"attempt": attempt.pk})
        self.assertContains(response, 'value="999"')

    def test_missing_location_rejected(self):
        response = self.client.post(self.url, self.payload(area="", ward="", street="", address_text=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Complaint.objects.exists())

    def test_invalid_ward_rejected(self):
        self.client.post(self.url, self.payload(ward=99999))
        self.assertFalse(Complaint.objects.exists())

    def test_invalid_images_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake = SimpleUploadedFile("x.jpg", b"not an image at all", content_type="image/jpeg")
        response = self.client.post(self.url, self.payload(image=fake))
        self.assertContains(response, "not a valid image")
        self.assertFalse(Complaint.objects.exists())

    @override_settings(MAX_IMAGE_SIZE_MB=0.001)
    def test_excessively_large_image_rejected(self):
        response = self.client.post(self.url, self.payload(image=make_upload("big.png", size=(300, 300), noise=True)))
        self.assertContains(response, "too large")
        self.assertFalse(Complaint.objects.exists())

    def test_stored_image_uses_random_name_and_loses_metadata(self):
        upload = make_upload("../../evil name.jpg", "JPEG", exif=True)
        self.client.post(self.url, self.payload(image=upload))
        image = ComplaintImage.objects.get()
        stored = os.path.basename(image.image.name)
        self.assertNotIn("evil", stored)
        self.assertRegex(stored, r"^[0-9a-f]{32}\.jpg$")
        with Image.open(os.path.join(settings.MEDIA_ROOT, image.image.name)) as saved:
            self.assertEqual(saved.format, "JPEG")
            self.assertEqual(len(saved.getexif()), 0)          # camera metadata removed

    def test_submission_is_atomic(self):
        with mock.patch("complaints.services.submission.ComplaintStatusHistory.objects.create",
                        side_effect=RuntimeError("boom")):
            response = self.client.post(self.url, self.payload(image=make_upload()))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not save your complaint")
        self.assertNotContains(response, "boom")
        self.assertEqual(
            (Complaint.objects.count(), ComplaintLocation.objects.count(), ComplaintImage.objects.count(),
             ComplaintStatusHistory.objects.count()), (0, 0, 0, 0))

    def test_script_in_text_is_escaped_on_detail_page(self):
        self.client.post(self.url, self.payload(
            title="Streetlight <script>alert(1)</script> broken",
            description="The streetlight is broken and <b>very</b> dark near the junction for three days now"))
        complaint = Complaint.objects.get()
        page = self.client.get(reverse("complaints:detail", args=[complaint.pk]))
        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;")


class PhotoOnlySubmissionTests(ComplaintTestCase):
    def test_submitting_a_photo_without_a_description_saves_nothing(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("complaints:new"), self.payload(description="", image=make_upload("pole.png")))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "required")
        self.assertFalse(Complaint.objects.exists())
        self.assertFalse(ComplaintImage.objects.exists())

    def test_a_short_description_is_refused_even_with_a_photo(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("complaints:new"), self.payload(description="Streetlight is broken", image=make_upload()))
        self.assertContains(response, "too short")
        self.assertFalse(Complaint.objects.exists())

    def test_text_without_a_photo_is_refused(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("complaints:new"), self.payload(image=None))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please upload an image related to your complaint before submitting.")
        self.assertFalse(Complaint.objects.exists())


class MandatoryPhotoTests(ComplaintTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.citizen)
        self.url = reverse("complaints:new")

    def test_the_form_marks_the_photo_as_required(self):
        page = self.client.get(self.url).content.decode()
        self.assertRegex(page, r'<input type="file" name="image"[^>]*required')
        self.assertIn("Photo of the problem", page)

    def test_every_kind_of_bad_photo_is_refused_and_nothing_is_saved(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = {"not an image": SimpleUploadedFile("a.jpg", b"plain text", content_type="image/jpeg"),
               "empty file": SimpleUploadedFile("a.png", b"", content_type="image/png"),
               "unsupported type": SimpleUploadedFile("a.gif", make_upload("a.png").read(), content_type="image/gif"),
               "script": SimpleUploadedFile("a.php", b"<?php ?>", content_type="image/png")}
        for label, upload in bad.items():
            response = self.client.post(self.url, self.payload(image=upload))
            self.assertEqual(response.status_code, 200, label)
        self.assertFalse(Complaint.objects.exists())

    def test_a_storage_failure_leaves_no_half_submitted_complaint(self):
        with mock.patch("complaints.services.submission.ComplaintImage.objects.create", side_effect=OSError("disk full")):
            response = self.client.post(self.url, self.payload())
        self.assertContains(response, "could not save your complaint")
        self.assertEqual((Complaint.objects.count(), ComplaintImage.objects.count()), (0, 0))
        self.assertNotContains(response, "submitted successfully")

    def test_the_service_refuses_a_complaint_without_a_photo(self):
        from complaints.forms import ComplaintForm
        from complaints.services import WorkflowError, submit_complaint
        data, files = self.form_args()
        form = ComplaintForm(data, files, citizen=self.citizen)
        self.assertTrue(form.is_valid())
        with self.assertRaisesMessage(WorkflowError, "upload an image"):
            submit_complaint(citizen=self.citizen, data=form.cleaned_data, image=None)
        self.assertFalse(Complaint.objects.exists())

    def test_the_photo_is_stored_with_the_complaint_and_shown_later(self):
        self.client.post(self.url, self.payload())
        c = Complaint.objects.get()
        image = c.images.get()
        self.assertEqual((image.kind, image.uploaded_by), ("EVIDENCE", self.citizen))
        page = self.client.get(reverse("complaints:detail", args=[c.pk])).content.decode()
        self.assertIn(reverse("complaints:image", args=[c.pk, image.pk]), page)
        self.assertEqual(self.client.get(reverse("complaints:image", args=[c.pk, image.pk])).status_code, 200)

    def test_old_complaints_without_a_photo_still_work_everywhere(self):
        from accounts.models import Role
        from accounts.tests.helpers import make_department, make_user
        old = Complaint.objects.create(citizen=self.citizen, title="Old complaint", description="Written before photos were compulsory here")
        ComplaintLocation.objects.create(complaint=old, ward=self.ward, street="Main", address_text="Main street address")
        self.assertEqual(self.client.get(reverse("complaints:detail", args=[old.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("complaints:my_complaints")).status_code, 200)
        Complaint.objects.filter(pk=old.pk).update(department=make_department("ELECTRICITY"), status="PENDING")
        officer = make_user("o@example.com", Role.OFFICER, department=make_department("ELECTRICITY"))
        self.client.force_login(officer)
        self.assertEqual(self.client.get(reverse("officer:detail", args=[old.pk])).status_code, 200)
        self.client.force_login(make_user("a@example.com", Role.ADMIN))
        self.assertEqual(self.client.get(reverse("adminpanel:complaint", args=[old.pk])).status_code, 200)

    def test_other_people_cannot_open_the_photo(self):
        from accounts.models import Role
        from accounts.tests.helpers import make_user
        self.client.post(self.url, self.payload())
        c = Complaint.objects.get()
        image = c.images.get()
        url = reverse("complaints:image", args=[c.pk, image.pk])
        self.client.force_login(make_user("other@example.com", Role.CITIZEN))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
