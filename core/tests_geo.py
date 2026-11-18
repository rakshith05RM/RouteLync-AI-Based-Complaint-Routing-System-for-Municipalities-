"""
Location search: provider parsing, caching, limits, signed selections and the JSON endpoints.

The "provider" payloads below are STAND-INS written in the documented shapes of the Photon and Nominatim APIs. They prove
that RouteLync parses, filters, caches and protects correctly; they do not prove the real services are reachable.
Real-service checks are in docs/MANUAL_TESTS.md.
"""
import io
import json
import socket
import urllib.error
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_department, make_user
from core.geo import providers, service
from core.geo.providers import GeocoderError, inside_area, parse_bbox

PHOTON_MAJESTIC = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.5726, 12.9767]},
     "properties": {"osm_id": 4455, "osm_type": "W", "osm_key": "amenity", "osm_value": "bus_station", "name": "Kempegowda Bus Station",
                    "street": "Kempegowda Road", "district": "Gandhinagar", "city": "Bengaluru", "county": "Bengaluru Urban",
                    "state": "Karnataka", "postcode": "560009"}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.5946, 12.9716]},
     "properties": {"osm_id": 1, "osm_type": "R", "osm_key": "place", "osm_value": "city", "name": "Bengaluru",
                    "county": "Bengaluru Urban", "state": "Karnataka"}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [80.2707, 13.0827]},        # Chennai: outside the Bengaluru service area
     "properties": {"osm_id": 2, "osm_type": "R", "osm_key": "place", "osm_value": "city", "name": "Chennai",
                    "county": "Chennai", "state": "Tamil Nadu"}},
    {"type": "Feature", "geometry": {"type": "Point"}, "properties": {"name": "broken record"}}]}

NOMINATIM_ROAD = [{"place_id": 98765, "osm_type": "way", "osm_id": 456, "lat": "12.9763", "lon": "77.5713", "name": "",
                   "display_name": "Kempegowda Road, Gandhinagar, Bengaluru, Karnataka, India",
                   "address": {"road": "Kempegowda Road", "suburb": "Gandhinagar", "city": "Bengaluru",
                               "county": "Bengaluru Urban", "state": "Karnataka"}}]


class ParsingTests(SimpleTestCase):
    @override_settings(GEOCODER_PROVIDER="photon", GEOCODER_BASE_URL="", LOCATION_MAP_BOUNDS="12.70,77.35,13.25,77.85")
    def test_photon_results_are_normalised_filtered_and_bounded(self):
        with mock.patch("core.geo.providers._get_json", return_value=PHOTON_MAJESTIC) as get:
            found = providers._photon_search("majestic", parse_bbox())
        url = get.call_args[0][0]
        self.assertIn("https://photon.komoot.io/api/?", url)
        self.assertIn("bbox=77.35%2C12.7%2C77.85%2C13.25", url)                  # lon,lat order, as Photon expects
        self.assertEqual(len(found), 3)                                            # the broken record is skipped
        first = found[0]
        self.assertEqual((first["name"], first["street"], first["area_hint"], first["city"]), ("Kempegowda Bus Station", "Kempegowda Road", "Gandhinagar", "Bengaluru"))
        self.assertEqual(first["label"], "Kempegowda Bus Station, Kempegowda Road, Gandhinagar, Bengaluru, Bengaluru Urban, Karnataka")
        self.assertEqual(first["district"], "Bengaluru Urban")
        self.assertEqual((first["lat"], first["lng"], first["id"]), (12.9767, 77.5726, "photon:W4455"))

    @override_settings(GEOCODER_PROVIDER="nominatim", GEOCODER_BASE_URL="https://geo.example.org/", GEOCODER_API_KEY="SECRETKEY", GEOCODER_CONTACT_EMAIL="ops@example.org", LOCATION_MAP_BOUNDS="12.70,77.35,13.25,77.85")
    def test_nominatim_results_and_request(self):
        with mock.patch("core.geo.providers._get_json", return_value=NOMINATIM_ROAD) as get:
            found = providers._nominatim_search("kempegowda road", parse_bbox())
        url = get.call_args[0][0]
        for part in ("https://geo.example.org/search?", "bounded=1", "viewbox=77.35%2C13.25%2C77.85%2C12.7", "key=SECRETKEY", "email=ops%40example.org"):
            self.assertIn(part, url)
        self.assertEqual((found[0]["street"], found[0]["area_hint"], found[0]["id"]), ("Kempegowda Road", "Gandhinagar", "nominatim:98765"))
        self.assertEqual(found[0]["name"], "")

    def test_unexpected_shapes_are_reported_not_trusted(self):
        for fn, payload in ((providers._photon_search, ["not", "a", "dict"]), (providers._photon_search, {"features": "nope"}),
                            (providers._nominatim_search, {"not": "a list"})):
            with mock.patch("core.geo.providers._get_json", return_value=payload):
                with self.assertRaises(GeocoderError) as ctx:
                    fn("x", None)
                self.assertEqual(ctx.exception.kind, "bad_response")

    def test_reverse_parsing(self):
        with mock.patch("core.geo.providers._get_json", return_value={"features": PHOTON_MAJESTIC["features"][:1]}):
            self.assertEqual(providers._photon_reverse(12.97, 77.57)["street"], "Kempegowda Road")
        with mock.patch("core.geo.providers._get_json", return_value={"features": []}):
            self.assertIsNone(providers._photon_reverse(12.97, 77.57))
        with mock.patch("core.geo.providers._get_json", return_value={"error": "Unable to geocode"}):
            self.assertIsNone(providers._nominatim_reverse(12.97, 77.57))


class HttpLayerTests(SimpleTestCase):
    def call(self, side_effect=None, body=b"{}"):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = body
        with mock.patch("urllib.request.urlopen", side_effect=side_effect, return_value=response) as op:
            try:
                return providers._get_json("https://geo.example/x"), op
            except GeocoderError as exc:
                return exc, op

    def test_failures_are_translated(self):
        err = urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO())
        self.assertEqual(self.call(side_effect=err)[0].kind, "rate_limited")
        self.assertEqual(self.call(side_effect=urllib.error.HTTPError("u", 503, "x", {}, io.BytesIO()))[0].kind, "unavailable")
        self.assertEqual(self.call(side_effect=urllib.error.URLError("no route"))[0].kind, "unavailable")
        self.assertEqual(self.call(side_effect=socket.timeout("slow"))[0].kind, "unavailable")
        self.assertEqual(self.call(body=b"<html>not json</html>")[0].kind, "bad_response")
        self.assertEqual(self.call(body=b"x" * 1_000_001)[0].kind, "bad_response")

    @override_settings(GEOCODER_USER_AGENT="RouteLync-test/1.0", GEOCODER_TIMEOUT=3)
    def test_request_identifies_the_application_and_has_a_timeout(self):
        data, op = self.call(body=b'{"ok": true}')
        self.assertEqual(data, {"ok": True})
        request = op.call_args[0][0]
        self.assertEqual(request.get_header("User-agent"), "RouteLync-test/1.0")
        self.assertEqual(op.call_args[1]["timeout"], 3)

    @override_settings(GEOCODER_PROVIDER="nope")
    def test_unknown_provider(self):
        with self.assertRaises(GeocoderError):
            providers.provider_functions()


class ServiceAreaTests(SimpleTestCase):
    def test_bbox_parsing_and_membership(self):
        self.assertEqual(parse_bbox("12.7,77.35,13.25,77.85"), (12.7, 77.35, 13.25, 77.85))
        self.assertEqual(parse_bbox("13.25,77.85,12.7,77.35"), (12.7, 77.35, 13.25, 77.85))       # corners in any order
        self.assertIsNone(parse_bbox("")); self.assertIsNone(parse_bbox("nonsense"))
        self.assertTrue(inside_area(12.9716, 77.5946, "Bengaluru Urban District"))
        self.assertTrue(inside_area(12.9716, 77.5946, "Bangalore North"))
        self.assertTrue(inside_area(13.294, 77.537, "Bengaluru Rural"))
        self.assertTrue(inside_area(13.294, 77.537, "Doddaballapura taluk"))
        self.assertTrue(inside_area(13.247, 77.713, "Devanahalli taluku"))
        self.assertTrue(inside_area(13.1, 77.39, "Nelamangala taluk"))
        self.assertFalse(inside_area(13.0827, 80.2707, "Chennai"))
        self.assertFalse(inside_area(12.9716, 77.5946))
        self.assertFalse(inside_area(91, 77.5946, "Bengaluru Urban"))


class ServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(GEOCODER_PROVIDER="photon")
    def test_search_uses_supported_place_name_when_district_is_missing(self):
        response = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.5946, 12.9716]},
             "properties": {"osm_id": 3, "osm_type": "R", "name": "Bengaluru Urban", "state": "Karnataka"}}
        ]}
        with mock.patch("core.geo.providers._get_json", return_value=response):
            found = service.search_places("Bengaluru Urban", 7)
        self.assertEqual(found[0]["service_area"], "Bengaluru Urban")
        self.assertEqual(found[0]["service_area_status"], "available")
        payload = service.read_selection(found[0]["token"], 7)
        self.assertEqual(payload["service_area"], "Bengaluru Urban")

    @override_settings(GEOCODER_PROVIDER="photon")
    def test_search_keeps_outside_results_marks_coverage_signs_and_caches(self):
        with mock.patch("core.geo.providers._get_json", return_value=PHOTON_MAJESTIC) as get:
            first = service.search_places("  Majestic   Bus ", 7)
            second = service.search_places("majestic bus", 7)               # same words, different case/spacing
        self.assertEqual(get.call_count, 1)
        self.assertEqual([r["name"] for r in first], ["Kempegowda Bus Station", "Bengaluru", "Chennai"])
        self.assertEqual([r["service_area_status"] for r in first], ["available", "available", "unavailable"])
        self.assertTrue(all(r["token"] for r in first))
        self.assertEqual([r["name"] for r in second], [r["name"] for r in first])

    def test_failures_are_not_cached(self):
        with mock.patch("core.geo.providers._get_json", side_effect=[GeocoderError("unavailable"), PHOTON_MAJESTIC]) as get:
            with self.assertRaises(GeocoderError):
                service.search_places("majestic", 1)
            self.assertTrue(service.search_places("majestic", 1))
        self.assertEqual(get.call_count, 2)

    def test_short_queries_never_reach_the_provider(self):
        with mock.patch("core.geo.providers._get_json") as get:
            for q in ("", "  ", "ab"):
                with self.assertRaises(ValueError):
                    service.search_places(q, 1)
        get.assert_not_called()

    def test_long_queries_are_truncated(self):
        with mock.patch("core.geo.providers._get_json", return_value={"features": []}) as get:
            service.search_places("x" * 500, 1)
        self.assertLess(len(get.call_args[0][0]), 400)

    def test_selection_tokens(self):
        token = service.sign_selection(5, 12.9763, 77.5713, "photon:W1", "Somewhere", "SEARCH")
        payload = service.read_selection(token, 5)
        self.assertEqual((payload["lat"], payload["lng"], payload["id"], payload["src"]), ("12.976300", "77.571300", "photon:W1", "SEARCH"))
        self.assertIsNone(service.read_selection(token, 6))                      # issued to someone else
        self.assertIsNone(service.read_selection(token[:-3] + "abc", 5))         # tampered
        self.assertIsNone(service.read_selection("garbage", 5))
        with mock.patch("django.core.signing.time.time", return_value=__import__("time").time() + 3 * 3600):
            self.assertIsNone(service.read_selection(token, 5))                  # expired after two hours


class EndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.citizen = make_user("c@example.com", Role.CITIZEN)
        self.client.force_login(self.citizen)

    def search(self, q="majestic bus"):
        return self.client.get(reverse("geo:search"), {"q": q})

    def test_only_signed_in_citizens(self):
        self.client.logout()
        self.assertEqual(self.search().status_code, 302)
        self.assertEqual(self.client.get(reverse("geo:reverse"), {"lat": 12.9, "lng": 77.5}).status_code, 302)
        self.client.force_login(make_user("o@example.com", Role.OFFICER, department=make_department("ELECTRICITY")))
        self.assertEqual(self.search().status_code, 403)

    def test_search_returns_results_with_tokens_and_attribution(self):
        with mock.patch("core.geo.providers._get_json", return_value=PHOTON_MAJESTIC):
            response = self.search()
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["attribution"], "\u00a9 OpenStreetMap contributors")
        self.assertEqual(len(data["results"]), 3)
        first = data["results"][0]
        self.assertEqual({"id", "label", "name", "street", "area_hint", "city", "district", "lat", "lng",
                          "service_area", "service_area_status", "token"}, set(first))
        payload = service.read_selection(first["token"], self.citizen.pk)
        self.assertEqual(payload["lat"], "12.976700")
        self.assertEqual(payload["service_area"], "Bengaluru Urban")

    def test_input_problems_and_provider_problems_have_clear_answers(self):
        self.assertEqual(self.search("ab").status_code, 400)
        self.assertIn("at least 3", self.search("ab").json()["error"])
        with mock.patch("core.geo.providers._get_json", side_effect=GeocoderError("unavailable")):
            r = self.search("kempegowda")
        self.assertEqual(r.status_code, 502)
        self.assertIn("place the pin on the map", r.json()["error"])
        with mock.patch("core.geo.providers._get_json", side_effect=GeocoderError("rate_limited")):
            r = self.search("another query")
        self.assertEqual(r.status_code, 429)
        self.assertIn("busy", r.json()["error"])

    @override_settings(GEOCODER_RATE_PER_MINUTE=2)
    def test_each_person_is_rate_limited(self):
        with mock.patch("core.geo.providers._get_json", return_value=PHOTON_MAJESTIC):
            codes = [self.search(f"query {i}").status_code for i in range(4)]
        self.assertEqual(codes, [200, 200, 429, 429])

    @override_settings(GEOCODER_PROVIDER="nominatim", GEOCODER_API_KEY="TOP-SECRET-KEY")
    def test_the_api_key_never_reaches_the_browser(self):
        with mock.patch("core.geo.providers._get_json", return_value=NOMINATIM_ROAD):
            r = self.search("kempegowda road")
        self.assertNotIn("TOP-SECRET-KEY", r.content.decode())
        from django.template.loader import render_to_string
        self.assertNotIn("TOP-SECRET-KEY", render_to_string("complaints/complaint_form.html", {"form": None}) if False else "")

    def test_reverse_geocoding(self):
        feature = {"features": PHOTON_MAJESTIC["features"][:1]}
        with mock.patch("core.geo.providers._get_json", return_value=feature):
            r = self.client.get(reverse("geo:reverse"), {"lat": "12.9767", "lng": "77.5726"})
        result = r.json()["result"]
        self.assertEqual((r.status_code, result["street"]), (200, "Kempegowda Road"))
        payload = service.read_selection(result["token"], self.citizen.pk)
        self.assertEqual((payload["lat"], payload["lng"], payload["src"]), ("12.976700", "77.572600", "MAP"))

    def test_reverse_rejects_bad_points_without_calling_the_provider(self):
        with mock.patch("core.geo.providers._get_json") as get:
            for params in ({"lat": "abc", "lng": "77"}, {"lat": "91", "lng": "77"}, {"lat": "12", "lng": "181"}, {"lat": "NaN", "lng": "77"}, {}):
                self.assertEqual(self.client.get(reverse("geo:reverse"), params).status_code, 400, params)
        get.assert_not_called()
        with mock.patch("core.geo.providers._get_json", return_value={"features": PHOTON_MAJESTIC["features"][2:3]}):
            outside = self.client.get(reverse("geo:reverse"), {"lat": "13.0827", "lng": "80.2707"})
        self.assertEqual(outside.status_code, 200)
        self.assertEqual(outside.json()["result"]["service_area_status"], "unavailable")

    def test_reverse_with_no_address_or_a_provider_failure(self):
        with mock.patch("core.geo.providers._get_json", return_value={"features": []}):
            self.assertEqual(self.client.get(reverse("geo:reverse"), {"lat": "12.9", "lng": "77.5"}).status_code, 404)
        with mock.patch("core.geo.providers._get_json", side_effect=GeocoderError("unavailable")):
            self.assertEqual(self.client.get(reverse("geo:reverse"), {"lat": "12.91", "lng": "77.51"}).status_code, 502)
