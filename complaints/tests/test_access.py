from django.db import IntegrityError, transaction
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_department, make_user
from complaints.models import Complaint, ComplaintImage, ComplaintLocation
from complaints.selectors import complaints_visible_to

from .helpers import ComplaintTestCase, make_upload


class ComplaintAccessTests(ComplaintTestCase):
    def setUp(self):
        super().setUp()
        self.other = make_user("other@example.com", Role.CITIZEN)
        self.mine = self.submit(self.citizen, image=True)
        self.theirs = self.submit(self.other)

    def submit(self, user, image=False):
        from complaints.services import submit_complaint
        from complaints.forms import ComplaintForm
        data, files = self.form_args()
        form = ComplaintForm(data, files, citizen=user)
        assert form.is_valid(), form.errors
        return submit_complaint(citizen=user, data=form.cleaned_data, image=form.cleaned_data["image"])

    def test_anonymous_redirected_to_login(self):
        for name, args in (("complaints:new", []), ("complaints:my_complaints", []),
                           ("complaints:detail", [self.mine.pk])):
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 302, name)

    def test_list_shows_only_own_complaints(self):
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("complaints:my_complaints"))
        self.assertContains(response, self.mine.reference)
        self.assertNotContains(response, self.theirs.reference)

    def test_empty_state_for_new_citizen(self):
        self.client.force_login(make_user("new@example.com", Role.CITIZEN))
        self.assertContains(self.client.get(reverse("complaints:my_complaints")), "not reported any problems")

    def test_cannot_open_another_citizens_complaint(self):
        self.client.force_login(self.citizen)
        self.assertEqual(self.client.get(reverse("complaints:detail", args=[self.theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("complaints:detail", args=[self.mine.pk])).status_code, 200)

    def test_non_citizens_cannot_submit_or_list(self):
        for role in (Role.OFFICER, Role.FIELD_WORKER, Role.ADMIN):
            self.client.force_login(make_user(f"{role}@example.com", role))
            self.assertEqual(self.client.get(reverse("complaints:new")).status_code, 403, role)
            self.assertEqual(self.client.post(reverse("complaints:new"), self.payload()).status_code, 403, role)

    def test_image_only_served_to_authorised_users(self):
        image = ComplaintImage.objects.get(complaint=self.mine)
        url = reverse("complaints:image", args=[self.mine.pk, image.pk])
        self.assertEqual(self.client.get(url).status_code, 302)                       # anonymous
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)                       # other citizen
        self.client.force_login(self.citizen)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)                                   # owner
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        b"".join(response.streaming_content)
        self.client.force_login(make_user("admin@example.com", Role.ADMIN))
        self.assertEqual(self.client.get(url).status_code, 200)                       # admin
        # image id with the wrong complaint id must not leak either
        wrong = reverse("complaints:image", args=[self.theirs.pk, image.pk])
        self.assertEqual(self.client.get(wrong).status_code, 404)

    def test_media_is_not_served_directly(self):
        image = ComplaintImage.objects.get(complaint=self.mine)
        self.client.force_login(self.citizen)
        self.assertEqual(self.client.get("/media/" + image.image.name).status_code, 404)

    def test_visibility_rules_per_role(self):
        elec, water = make_department("ELECTRICITY"), make_department("WATER_SUPPLY")
        self.mine.department = elec
        self.mine.save()
        e_officer = make_user("e@example.com", Role.OFFICER, department=elec)
        w_officer = make_user("w@example.com", Role.OFFICER, department=water)
        worker = make_user("fw@example.com", Role.FIELD_WORKER, department=elec)
        admin = make_user("a@example.com", Role.ADMIN)
        self.assertEqual(set(complaints_visible_to(self.citizen)), {self.mine})
        self.assertEqual(set(complaints_visible_to(e_officer)), {self.mine})
        self.assertEqual(set(complaints_visible_to(w_officer)), set())     # other department
        self.assertEqual(set(complaints_visible_to(worker)), set())        # until assignments exist
        self.assertEqual(set(complaints_visible_to(admin)), {self.mine, self.theirs})
        self.assertEqual(set(complaints_visible_to(__import__("django.contrib.auth.models", fromlist=["AnonymousUser"]).AnonymousUser())), set())

    def test_officer_without_profile_sees_nothing_not_unrouted_complaints(self):
        from django.contrib.auth import get_user_model
        orphan = get_user_model().objects.create_user("o@example.com", "x", full_name="O", role=Role.OFFICER)
        self.assertEqual(complaints_visible_to(orphan).count(), 0)   # unrouted complaints have department=NULL


class LocationConstraintTests(ComplaintTestCase):
    def test_database_rejects_bad_coordinates(self):
        complaint = Complaint.objects.create(citizen=self.citizen, title="Some title", description="x" * 30)
        for lat, lon in ((91, 10), (10, 181), (10, None), (None, 10)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                ComplaintLocation.objects.create(complaint=complaint, ward=self.ward, street="Main",
                                                 address_text="Main street address", latitude=lat, longitude=lon)
