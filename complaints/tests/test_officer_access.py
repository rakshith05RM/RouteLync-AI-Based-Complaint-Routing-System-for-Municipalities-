import json

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import ComplaintStatus as S

from .officer_helpers import OfficerTestCase


class OfficerAccessTests(OfficerTestCase):
    def urls(self, pk):
        return [reverse("officer:dashboard"), reverse("officer:locations"), reverse("officer:map"),
                reverse("officer:detail", args=[pk])]

    def test_anonymous_is_sent_to_login(self):
        c = self.make()
        for url in self.urls(c.pk):
            self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_other_roles_get_403_on_every_officer_page(self):
        c = self.make()
        for role in (Role.CITIZEN, Role.FIELD_WORKER, Role.ADMIN):
            self.client.force_login(make_user(f"other-{role}@example.com", role))
            for url in self.urls(c.pk):
                self.assertEqual(self.client.get(url).status_code, 403, f"{role} {url}")

    def test_officer_sees_only_own_department(self):
        mine = self.make(title="Streetlight broken at corner")
        theirs = self.make(dept=self.water, title="Water pipe leaking badly")
        self.login_officer()
        page = self.client.get(reverse("officer:dashboard")).content.decode()
        self.assertIn(mine.reference, page)
        self.assertNotIn(theirs.reference, page)
        self.assertNotIn("Water pipe leaking badly", page)
        self.assertNotIn("Water Supply", page)

    def test_unrouted_complaints_are_never_listed(self):
        waiting = self.make(status=S.NEEDS_VERIFICATION, dept=None, title="Waiting for an administrator")
        self.login_officer()
        self.assertNotContains(self.client.get(reverse("officer:dashboard")), waiting.reference)
        self.assertEqual(self.client.get(reverse("officer:detail", args=[waiting.pk])).status_code, 404)

    def test_detail_of_another_department_is_404(self):
        theirs = self.make(dept=self.water)
        self.login_officer()
        self.assertEqual(self.client.get(reverse("officer:detail", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("officer:detail", args=[999999])).status_code, 404)

    def test_other_department_image_is_not_served(self):
        from complaints.models import ComplaintImage
        from complaints.tests.helpers import make_upload
        from complaints.services.submission import sanitize_image
        theirs = self.make(dept=self.water)
        image = ComplaintImage.objects.create(complaint=theirs, image=sanitize_image(make_upload()))
        self.login_officer()
        self.assertEqual(self.client.get(reverse("complaints:image", args=[theirs.pk, image.pk])).status_code, 404)
        self.client.force_login(self.water_officer)
        self.assertEqual(self.client.get(reverse("complaints:image", args=[theirs.pk, image.pk])).status_code, 200)

    def test_map_data_scoped_and_has_no_personal_information(self):
        mine = self.make(lat=12.925, lng=77.5938)
        self.make(dept=self.water, lat=12.93, lng=77.59, title="Other department complaint")
        self.login_officer()
        response = self.client.get(reverse("officer:map"))
        markers = response.context["markers"]
        self.assertEqual([m["id"] for m in markers], [mine.pk])
        blob = json.dumps(markers)
        for private in (self.citizen.full_name, self.citizen.email, self.citizen.phone or "no-phone-set", "Other department"):
            self.assertNotIn(private, blob)
        self.assertEqual(set(markers[0]), {"id", "ref", "title", "area", "ward", "priority", "priority_label",
                                           "status", "lat", "lng", "url"})

    def test_list_does_not_run_a_query_per_row(self):
        self.login_officer()

        def queries():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse("officer:dashboard"))
            return len(ctx)

        for _ in range(3):
            self.make(lat=12.9, lng=77.5)
        few = queries()
        for _ in range(12):
            self.make(lat=12.9, lng=77.5)
        self.assertEqual(queries(), few, "the number of queries grows with the number of rows (N+1)")

    def test_leaflet_is_served_locally_and_not_from_a_cdn(self):
        self.login_officer()
        page = self.client.get(reverse("officer:map")).content.decode()
        self.assertIn("vendor/leaflet/leaflet.js", page)
        self.assertNotIn("unpkg.com", page)
