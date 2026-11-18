from django.urls import reverse

from complaints.models import ComplaintStatus as S

from .officer_helpers import OfficerTestCase

LOC = "officer:locations"


class DrillDownTests(OfficerTestCase):
    def setUp(self):
        super().setUp()
        self.login_officer()
        # Jayanagar ward 154: 3 on "4th Main Road" (one written in other case, one overdue), 1 on "5th Cross"
        self.make(street="4th Main Road")
        self.make(street="4TH main road", hours_ago=30, sla_hours=24)
        self.make(street="4th Main Road")
        self.make(street="5th Cross")
        self.make(ward=self.ward2, street="Main Street")                       # Jayanagar ward 155
        self.make(ward=self.other_ward, street="Hope Farm Road")               # Whitefield
        self.make(street="4th Main Road", status=S.CLOSED)                      # closed work is not "active"
        self.make(dept=self.water, street="4th Main Road")                      # other department

    def level(self, **params):
        response = self.client.get(reverse(LOC), params)
        self.assertEqual(response.status_code, 200)
        return response.context

    def test_area_level_counts_active_complaints(self):
        ctx = self.level()
        self.assertEqual(ctx["level"], "area")
        self.assertEqual([(r["label"], r["active"], r["overdue"]) for r in ctx["rows"]],
                         [("Jayanagar", 5, 1), ("Whitefield", 1, 0)])

    def test_ward_level(self):
        ctx = self.level(area=self.area.pk)
        self.assertEqual(ctx["level"], "ward")
        self.assertEqual([(r["label"], r["active"]) for r in ctx["rows"]], [(154, 4), (155, 1)])

    def test_street_level_merges_spelling_variants(self):
        ctx = self.level(area=self.area.pk, ward=self.ward.pk)
        self.assertEqual(ctx["level"], "street")
        rows = {r["key"]: (r["active"], r["overdue"]) for r in ctx["rows"]}
        self.assertEqual(rows, {"4th main road": (3, 1), "5th cross": (1, 0)})

    def test_street_level_lists_the_complaints(self):
        ctx = self.level(area=self.area.pk, ward=self.ward.pk, street="4th main road")
        self.assertEqual(len(ctx["complaints"]), 3)                              # closed and other-department excluded
        page = self.client.get(reverse(LOC), {"area": self.area.pk, "ward": self.ward.pk, "street": "4th main road"})
        self.assertContains(page, "Open these in the full complaints list")
        self.assertContains(page, 'aria-current="page"')

    def test_breadcrumb_links_walk_back_up(self):
        page = self.client.get(reverse(LOC), {"area": self.area.pk, "ward": self.ward.pk})
        self.assertContains(page, "Electricity")
        self.assertContains(page, f"?area={self.area.pk}")
        self.assertContains(page, "Ward 154")

    def test_bad_ids_fall_back_to_a_higher_level(self):
        self.assertEqual(self.level(area="abc")["level"], "area")
        self.assertEqual(self.level(area="999999")["level"], "area")
        self.assertEqual(self.level(area=self.area.pk, ward=self.other_ward.pk)["level"], "ward")  # ward not in that area
        self.assertEqual(self.level(street="4th main road")["complaints"], [])                    # street without a ward

    def test_other_departments_never_leak_into_counts(self):
        self.client.force_login(self.water_officer)
        ctx = self.level()
        self.assertEqual([(r["label"], r["active"]) for r in ctx["rows"]], [("Jayanagar", 1)])

    def test_empty_department(self):
        from accounts.models import Role
        from accounts.tests.helpers import make_department, make_user
        self.client.force_login(make_user("new@example.com", Role.OFFICER, department=make_department("ROADS")))
        self.assertContains(self.client.get(reverse(LOC)), "no active complaints at this level")


class MapViewTests(OfficerTestCase):
    def setUp(self):
        super().setUp()
        self.login_officer()

    def test_only_complaints_with_gps_are_drawn_and_counts_explain_the_gap(self):
        self.make(lat=12.925, lng=77.5938)
        self.make(lat=12.93, lng=77.60)
        self.make()                                                                # no GPS
        response = self.client.get(reverse("officer:map"))
        self.assertEqual(len(response.context["markers"]), 2)
        self.assertEqual((response.context["total"], response.context["missing_gps"]), (3, 1))
        self.assertContains(response, "1 more has no GPS")
        self.assertContains(response, 'id="map-data"')

    def test_map_respects_filters(self):
        self.make(lat=12.9, lng=77.5, priority="HIGH")
        self.make(lat=12.9, lng=77.5, priority="LOW")
        response = self.client.get(reverse("officer:map"), {"priority": "HIGH"})
        self.assertEqual(len(response.context["markers"]), 1)

    def test_marker_titles_are_escaped_in_the_json_blob(self):
        self.make(lat=12.9, lng=77.5, title="Pole <script>alert(1)</script>")
        page = self.client.get(reverse("officer:map")).content.decode()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("\\u003Cscript\\u003E", page)

    def test_empty_map_message(self):
        self.assertContains(self.client.get(reverse("officer:map")), "No complaints with a GPS location")
