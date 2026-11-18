from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone

from complaints.models import ComplaintStatus as S
from departments.models import Area, Priority as P, Ward

from .officer_helpers import OfficerTestCase

DASH = "officer:dashboard"


class FilterTests(OfficerTestCase):
    def setUp(self):
        super().setUp()
        self.login_officer()

    def refs(self, **params):
        response = self.client.get(reverse(DASH), params)
        self.assertEqual(response.status_code, 200)
        return [c.reference for c in response.context["complaints"]]

    def test_default_hides_closed_and_rejected_only(self):
        open_one = self.make(status=S.PENDING)
        resolved = self.make(status=S.RESOLVED)
        closed = self.make(status=S.CLOSED)
        rejected = self.make(status=S.REJECTED)
        shown = self.refs()
        self.assertIn(open_one.reference, shown)
        self.assertIn(resolved.reference, shown)
        self.assertNotIn(closed.reference, shown)
        self.assertNotIn(rejected.reference, shown)
        self.assertEqual(len(self.refs(status="ALL")), 4)
        self.assertEqual(self.refs(status="CLOSED"), [closed.reference])

    def test_area_ward_and_street(self):
        a = self.make(street="4th Main Road")
        b = self.make(ward=self.ward2, street="5th Cross")
        c = self.make(ward=self.other_ward, street="Hope Farm Road")
        self.assertEqual(set(self.refs(area=self.area.pk)), {a.reference, b.reference})
        self.assertEqual(self.refs(ward=self.ward2.pk), [b.reference])
        self.assertEqual(self.refs(street="4TH main road"), [a.reference])         # exact, case-insensitive
        self.assertEqual(self.refs(area=self.other_area.pk, ward=self.other_ward.pk), [c.reference])
        self.assertEqual(self.refs(street="4th Main"), [])                          # partial street = no exact match

    def test_ward_outside_selected_area_is_reported_and_ignored(self):
        self.make()
        response = self.client.get(reverse(DASH), {"area": self.area.pk, "ward": self.other_ward.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is not in Jayanagar")
        self.assertEqual(len(response.context["complaints"]), 1)      # the bad ward filter is dropped, area still applies

    def test_status_priority_and_confidence(self):
        a = self.make(status=S.IN_PROGRESS, priority=P.HIGH, confidence=0.95)
        b = self.make(status=S.PENDING, priority=P.LOW, confidence=0.40)
        self.assertEqual(self.refs(status="IN_PROGRESS"), [a.reference])
        self.assertEqual(self.refs(priority="LOW"), [b.reference])
        self.assertEqual(self.refs(min_confidence=90), [a.reference])
        self.assertEqual(set(self.refs(min_confidence=40)), {a.reference, b.reference})
        self.assertEqual(self.refs(min_confidence=100), [])

    def test_date_range_is_inclusive_of_both_days(self):
        old = self.make(hours_ago=24 * 10)
        recent = self.make(hours_ago=2)
        today = timezone.localdate()
        self.assertEqual(self.refs(date_from=today - timedelta(days=1)), [recent.reference])
        self.assertEqual(self.refs(date_to=today - timedelta(days=5)), [old.reference])
        self.assertEqual(set(self.refs(date_from=today - timedelta(days=30), date_to=today)), {old.reference, recent.reference})
        self.assertEqual(self.refs(date_from=today + timedelta(days=1)), [])

    def test_reversed_dates_are_reported(self):
        self.make()
        response = self.client.get(reverse(DASH), {"date_from": "2026-05-10", "date_to": "2026-05-01"})
        self.assertContains(response, "end date is before")

    def test_overdue_filter(self):
        late = self.make(hours_ago=30, sla_hours=24)
        self.make(hours_ago=1, sla_hours=24)
        self.make(hours_ago=30, sla_hours=24, status=S.RESOLVED)      # resolved work is not "overdue"
        self.assertEqual(self.refs(overdue="on"), [late.reference])

    def test_combined_filters(self):
        target = self.make(ward=self.ward2, priority=P.HIGH, status=S.PENDING)
        self.make(ward=self.ward2, priority=P.LOW, status=S.PENDING)
        self.make(ward=self.ward, priority=P.HIGH, status=S.PENDING)
        self.assertEqual(self.refs(ward=self.ward2.pk, priority="HIGH", status="PENDING"), [target.reference])

    def test_garbage_parameters_never_crash(self):
        self.make()
        for params in ({"ward": "abc"}, {"area": "999999"}, {"date_from": "not-a-date"}, {"min_confidence": "xyz"},
                       {"min_confidence": "500"}, {"status": "HACKED"}, {"priority": "???"}, {"sort": "'; DROP TABLE"},
                       {"q": "x" * 500}, {"page": "abc"}):
            response = self.client.get(reverse(DASH), params)
            self.assertIn(response.status_code, (200, 404), params)

    def test_empty_states(self):
        page = self.client.get(reverse(DASH))
        self.assertContains(page, "no open complaints for Electricity")
        self.make()
        filtered = self.client.get(reverse(DASH), {"priority": "CRITICAL"})
        self.assertContains(filtered, "No complaints match these filters")


class SearchTests(OfficerTestCase):
    def setUp(self):
        super().setUp()
        self.login_officer()
        self.other_citizen = __import__("accounts.tests.helpers", fromlist=["make_user"]).make_user(
            "ravi@example.com", full_name="Ravi Kumar")

    def refs(self, q):
        return [c.reference for c in self.client.get(reverse(DASH), {"q": q}).context["complaints"]]

    def test_search_by_complaint_id_in_several_forms(self):
        a, b = self.make(), self.make()
        for q in (a.reference, a.reference.lower(), str(a.pk), f"RL{a.pk}"):
            self.assertEqual(self.refs(q), [a.reference], q)
        self.assertEqual(self.refs("999999"), [])

    def test_search_by_citizen_name(self):
        a = self.make(citizen=self.other_citizen)
        self.make()
        self.assertEqual(self.refs("ravi"), [a.reference])
        self.assertEqual(self.refs("Kumar"), [a.reference])

    def test_search_by_keyword_street_area_and_landmark(self):
        a = self.make(title="Transformer humming", description="Loud noise near the market", street="Temple Road", landmark="Opposite bakery")
        self.make(title="Streetlight out")
        self.assertEqual(self.refs("transformer"), [a.reference])
        self.assertEqual(self.refs("noise"), [a.reference])
        self.assertEqual(self.refs("temple"), [a.reference])
        self.assertEqual(self.refs("bakery"), [a.reference])
        self.assertEqual(len(self.refs("jayanagar")), 2)

    def test_every_word_must_match(self):
        a = self.make(title="Transformer humming", street="Temple Road")
        self.make(title="Transformer sparking", street="Main Road")
        self.assertEqual(self.refs("transformer temple"), [a.reference])
        self.assertEqual(self.refs("transformer nonexistentword"), [])

    def test_search_cannot_reach_other_departments(self):
        self.make(dept=self.water, title="Unique waterword leak")
        self.assertEqual(self.refs("waterword"), [])

    def test_injection_style_input_is_just_text(self):
        self.make()
        for q in ("' OR 1=1 --", "\"; DROP TABLE complaints_complaint; --", "%", "_", "<script>alert(1)</script>"):
            self.assertEqual(self.refs(q), [], q)
        self.assertEqual(len(self.refs("")), 1)


class SortingTests(OfficerTestCase):
    def setUp(self):
        super().setUp()
        self.login_officer()
        self.crit_late = self.make(priority=P.CRITICAL, hours_ago=5, sla_hours=4, status=S.IN_PROGRESS, title="A crit")
        self.high = self.make(priority=P.HIGH, hours_ago=20, sla_hours=12, status=S.PENDING, ward=self.ward2, title="B high")
        self.low = self.make(priority=P.LOW, hours_ago=3, sla_hours=72, status=S.DEPARTMENT_ASSIGNED, title="C low")
        self.nosla = self.make(priority=P.MEDIUM, hours_ago=10, status=S.PENDING, title="D none")
        type(self.nosla).objects.filter(pk=self.nosla.pk).update(sla_deadline=None)

    def order(self, sort=None):
        params = {"sort": sort} if sort else {}
        return [c.title for c in self.client.get(reverse(DASH), params).context["complaints"]]

    def test_default_is_priority_then_deadline(self):
        self.assertEqual(self.order(), ["A crit", "B high", "D none", "C low"])

    def test_newest_and_oldest(self):
        self.assertEqual(self.order("newest"), ["C low", "A crit", "D none", "B high"])
        self.assertEqual(self.order("oldest"), ["B high", "D none", "A crit", "C low"])

    def test_sla_deadline_puts_missing_deadlines_last(self):
        self.assertEqual(self.order("sla"), ["B high", "A crit", "C low", "D none"][:3] + ["D none"])
        self.assertEqual(self.order("sla")[-1], "D none")

    def test_status_follows_lifecycle_order(self):
        self.assertEqual(self.order("status")[0], "C low")           # DEPARTMENT_ASSIGNED first
        self.assertEqual(self.order("status")[-1], "A crit")         # IN_PROGRESS last

    def test_area_and_ward(self):
        self.assertEqual(self.order("ward")[-1], "B high")           # ward 155 after ward 154
        self.assertEqual(self.order("area")[-1], "B high")

    def test_unknown_sort_falls_back_to_default(self):
        self.assertEqual(self.order("bogus"), self.order())


class PaginationAndSummaryTests(OfficerTestCase):
    def setUp(self):
        super().setUp()
        self.login_officer()

    def test_pages_of_fifteen_keep_the_filters(self):
        for _ in range(20):
            self.make(priority=P.HIGH)
        for _ in range(3):
            self.make(priority=P.LOW)
        first = self.client.get(reverse(DASH), {"priority": "HIGH"})
        self.assertEqual(len(first.context["complaints"]), 15)
        self.assertContains(first, "20 complaints")
        self.assertContains(first, "priority=HIGH&amp;page=2")
        second = self.client.get(reverse(DASH), {"priority": "HIGH", "page": 2})
        self.assertEqual(len(second.context["complaints"]), 5)
        self.assertEqual(self.client.get(reverse(DASH), {"page": 99}).status_code, 404)

    def test_summary_cards_count_correctly_and_ignore_filters(self):
        self.make(status=S.PENDING)
        self.make(status=S.PENDING, hours_ago=30, sla_hours=24, priority=P.HIGH)       # overdue + urgent
        self.make(status=S.IN_PROGRESS, priority=P.CRITICAL)
        self.make(status=S.ASSIGNED_TO_WORKER)
        self.make(status=S.RESOLVED, hours_ago=50)
        self.make(status=S.CLOSED)
        self.make(dept=self.water, status=S.PENDING)                                    # other department
        summary = self.client.get(reverse(DASH), {"priority": "LOW"}).context["summary"]
        self.assertEqual(summary, {"open": 5, "pending": 2, "in_progress": 2, "overdue": 1, "urgent": 2, "escalated": 0, "awaiting": 0})

    def test_sla_and_confidence_shown_in_rows(self):
        self.make(hours_ago=30, sla_hours=24, confidence=0.87)
        page = self.client.get(reverse(DASH))
        self.assertContains(page, "Overdue by 6 h")
        self.assertContains(page, "87%")
