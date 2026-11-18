"""Location rules enforced on the server, whatever the browser sends."""
import time
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import Complaint, ComplaintLocation
from core.geo import service

from .helpers import ComplaintTestCase


class LocationRulesTests(ComplaintTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.citizen)
        self.url = reverse("complaints:new")

    def token(self, lat=12.9763, lng=77.5713, place="photon:W42",
              label="4th Main Road, Jayanagar, Bengaluru Urban", src="SEARCH", user=None,
              district="Bengaluru Urban", area_hint="Jayanagar"):
        return service.sign_selection((user or self.citizen).pk, lat, lng, place, label, src,
                                      district=district, area_hint=area_hint)

    def post(self, **over):
        return self.client.post(self.url, self.payload(**over))

    def test_a_missing_location_is_refused_and_nothing_is_replaced_with_a_default(self):
        response = self.post(latitude="", longitude="")
        self.assertContains(response, "Please choose the location of the problem: search for it, tap the map, or use your current location.")
        self.assertFalse(Complaint.objects.exists())

    def test_a_location_outside_the_service_area_is_refused(self):
        response = self.post(latitude="13.0827", longitude="80.2707",
                             location_token=self.token(13.0827, 80.2707, district="Chennai", area_hint="Chennai"))
        self.assertContains(response, "serves only Bengaluru Urban and Bengaluru Rural")
        self.assertFalse(Complaint.objects.exists())
        self.assertEqual(self.post(latitude="12.9", longitude="").status_code, 200)        # half a location
        self.assertFalse(Complaint.objects.exists())

    def test_service_area_cannot_be_disabled_or_changed_by_a_browser_value(self):
        response = self.post(latitude="13.0827", longitude="80.2707",
                             location_token=self.token(13.0827, 80.2707, district="Chennai", area_hint="Chennai"),
                             location_source="SEARCH")
        self.assertContains(response, "serves only Bengaluru Urban and Bengaluru Rural")
        self.assertFalse(Complaint.objects.exists())

    def test_a_verified_selection_is_stored_with_the_complaint(self):
        self.post(latitude="12.976300", longitude="77.571300", location_token=self.token(), location_source="GPS")
        loc = Complaint.objects.get().location
        self.assertEqual((str(loc.latitude), str(loc.longitude)), ("12.976300", "77.571300"))
        self.assertEqual((loc.formatted_address, loc.place_id, loc.location_source),
                         ("4th Main Road, Jayanagar, Bengaluru Urban", "photon:W42", "SEARCH"))
        self.assertEqual(loc.area_id, self.area.pk)

    def test_an_address_cannot_be_paired_with_different_coordinates(self):
        response = self.post(latitude="12.9900", longitude="77.6000", location_token=self.token())     # token is for 12.9763, 77.5713
        self.assertContains(response, "do not match")
        self.assertFalse(Complaint.objects.exists())

    def test_forged_expired_or_borrowed_tokens_are_refused(self):
        good = self.token()
        for label, token in (("tampered", good[:-4] + "abcd"), ("garbage", "not-a-token"),
                             ("someone else's", self.token(user=make_user("other@example.com", Role.CITIZEN)))):
            response = self.post(latitude="12.976300", longitude="77.571300", location_token=token)
            self.assertContains(response, "selection has expired", msg_prefix=label)
        with mock.patch("django.core.signing.time.time", return_value=time.time() + 3 * 3600):
            self.assertContains(self.post(latitude="12.976300", longitude="77.571300", location_token=good), "selection has expired")
        self.assertFalse(Complaint.objects.exists())

    def test_a_hand_placed_pin_waits_for_server_verification(self):
        response = self.post(location_token="", location_source="GPS")
        self.assertContains(response, "Please select a searched place or wait for the map to verify")
        self.assertFalse(Complaint.objects.exists())

    def test_the_browser_cannot_claim_a_verified_source_without_a_token(self):
        for claim in ("SEARCH", "ANYTHING", ""):
            Complaint.objects.all().delete()
            response = self.post(location_token="", location_source=claim)
            self.assertContains(response, "Please select a searched place or wait for the map to verify", msg_prefix=claim)
            self.assertFalse(Complaint.objects.exists())

    def test_coordinates_are_rounded_not_replaced(self):
        self.post(latitude="12.97634567891", longitude="77.57131234567")
        loc = Complaint.objects.get().location
        self.assertEqual((str(loc.latitude), str(loc.longitude)), ("12.976346", "77.571312"))

    @override_settings(LOCATION_MAP_BOUNDS="12.70,77.35,13.25,77.85")
    def test_the_form_page_has_the_search_and_map_with_accessible_markup(self):
        page = self.client.get(self.url).content.decode()
        for expected in ('id="location-search"', 'role="combobox"', 'aria-controls="location-results"', 'role="listbox"', 'id="location-map"',
                         'data-search-url="/geo/search/"', 'data-reverse-url="/geo/reverse/"', 'data-bbox="12.70,77.35,13.25,77.85"',
                         'name="location_token"', 'name="location_source"', "vendor/leaflet/leaflet.js", "js/location_picker.js", 'aria-live="polite"'):
            self.assertIn(expected, page)
        self.assertIn('name="location_search"', page)
        self.assertRegex(page, r'<select[^>]*name="area"[^>]*>')
        self.assertNotRegex(page, r'<select[^>]*name="area"[^>]*required')
        self.assertNotRegex(page, r'<select[^>]*name="ward"[^>]*required')
        self.assertNotIn("api_key", page.lower())

    def test_citizen_and_admin_details_render_the_complaint_map(self):
        complaint = Complaint.objects.create(
            citizen=self.citizen, title="Streetlight not working",
            description="The streetlight near the junction has not worked for several days.")
        ComplaintLocation.objects.create(
            complaint=complaint, area=self.area, ward=self.ward, address_text="4th Main Road, Jayanagar",
            latitude="12.925000", longitude="77.593800")

        citizen_page = self.client.get(reverse("complaints:detail", args=[complaint.pk]))
        self.assertContains(citizen_page, 'id="complaint-map"')
        self.assertContains(citizen_page, 'data-lat="12.925000"')
        self.assertContains(citizen_page, "js/complaint_map.js")

        admin = make_user("admin@example.com", Role.ADMIN)
        self.client.force_login(admin)
        admin_page = self.client.get(reverse("adminpanel:complaint", args=[complaint.pk]))
        self.assertContains(admin_page, 'id="complaint-map"')
        self.assertContains(admin_page, 'data-lng="77.5938"')
        self.assertContains(admin_page, "js/complaint_map.js")

    def test_the_search_script_never_inserts_service_text_as_html(self):
        script = (Path(settings.BASE_DIR) / "static/js/location_picker.js").read_text()
        for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(unsafe, script)
        self.assertIn("textContent", script)
        self.assertIn("AbortController", script)          # a newer search cancels the older one
        self.assertIn("350", script)                      # debounce

    def test_the_selection_survives_a_rejected_description(self):
        response = self.post(description="I am testing this website", latitude="12.976300", longitude="77.571300", location_token=self.token())
        self.assertContains(response, "Not submitted")
        from complaints.models import SubmissionAttempt
        a = SubmissionAttempt.objects.get()
        self.assertEqual((str(a.latitude), str(a.longitude)), ("12.976300", "77.571300"))
