from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests.helpers import make_user
from audit.models import AuditLog
from complaints.models import Complaint, ComplaintStatus as S, DuplicateFlag, DuplicateStatus
from complaints.services import WorkflowError, find_possible_duplicates, flag_possible_duplicates, review_duplicate
from notifications.models import Notification

from .workflow_helpers import WorkflowTestCase

POTHOLE_A = ("Large pothole on 4th Main Road", "There is a very large pothole in the middle of 4th Main Road near the metro station and bikes are skidding")
POTHOLE_B = ("Huge pothole on 4th Main Road", "A huge pothole has formed on 4th Main Road near the metro station and many bikes are skidding there")


class DetectionTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.complaint.delete()
        self.older = self.make(title=POTHOLE_A[0], description=POTHOLE_A[1], hours_ago=5, street="4th Main Road")

    def newer(self, **kw):
        kw.setdefault("title", POTHOLE_B[0])
        kw.setdefault("description", POTHOLE_B[1])
        kw.setdefault("street", "4th Main Road")
        kw.setdefault("hours_ago", 1)
        return self.make(**kw)

    def test_similar_complaint_on_the_same_street_is_flagged(self):
        c = self.newer()
        found = find_possible_duplicates(c)
        self.assertEqual([o.pk for o, _, _ in found], [self.older.pk])
        self.assertGreater(found[0][1], 0.65)
        self.assertEqual(found[0][2], "same street")
        self.assertEqual(flag_possible_duplicates(c), 1)
        flag = DuplicateFlag.objects.get()
        self.assertEqual((flag.complaint, flag.possible_duplicate_of, flag.status), (c, self.older, DuplicateStatus.PENDING))
        self.assertEqual(flag_possible_duplicates(c), 0)                        # running it again adds nothing

    def test_different_problems_are_not_flagged(self):
        c = self.newer(title="Garbage not collected", description="Garbage has not been collected from our street for a whole week now")
        self.assertEqual(find_possible_duplicates(c), [])

    def test_only_older_complaints_are_candidates(self):
        c = self.newer()
        self.assertEqual(find_possible_duplicates(self.older), [])
        self.assertEqual(len(find_possible_duplicates(c)), 1)

    def test_other_wards_old_and_finished_complaints_are_ignored(self):
        self.older.delete()
        self.make(title=POTHOLE_A[0], description=POTHOLE_A[1], hours_ago=5, ward=self.ward2)                    # other ward
        self.make(title=POTHOLE_A[0], description=POTHOLE_A[1], hours_ago=24 * 40)                              # too old
        self.make(title=POTHOLE_A[0], description=POTHOLE_A[1], hours_ago=6, status=S.CLOSED)                   # finished
        self.make(title=POTHOLE_A[0], description=POTHOLE_A[1], hours_ago=6, status=S.RESOLVED)
        self.assertEqual(find_possible_duplicates(self.newer()), [])

    def test_waiting_for_verification_complaints_are_candidates(self):
        self.older.delete()
        self.make(title=POTHOLE_A[0], description=POTHOLE_A[1], hours_ago=5, status=S.NEEDS_VERIFICATION, dept=None)
        self.assertEqual(len(find_possible_duplicates(self.newer())), 1)

    def test_same_ward_only_needs_a_higher_similarity(self):
        c = self.newer(street="Totally Different Street")
        self.assertEqual(find_possible_duplicates(c), [])                          # similar words alone are not enough without a location match
        with override_settings(DUPLICATE_THRESHOLD_WARD=0.3):
            found = find_possible_duplicates(c)
        self.assertEqual([r for _, _, r in found], ["same ward"])

    def test_nearby_gps_counts_as_the_same_place(self):
        self.older.delete()
        a = self.make(title=POTHOLE_A[0], description=POTHOLE_A[1], hours_ago=5, street="4th Main", lat=12.92500, lng=77.59380)
        c = self.newer(street="Fourth Main Rd", lat=12.92510, lng=77.59385)           # about 12 metres away
        self.assertEqual([(o.pk, r) for o, _, r in find_possible_duplicates(c)], [(a.pk, "nearby location")])
        far = self.newer(street="Elsewhere Road", lat=12.9400, lng=77.6100)           # about 2 km away
        with override_settings(DUPLICATE_THRESHOLD_WARD=0.95):
            self.assertNotIn(a.pk, [o.pk for o, _, _ in find_possible_duplicates(far)])

    def test_street_names_compare_case_and_spacing_insensitively(self):
        c = self.newer(street="  4TH   main road ")
        self.assertEqual(find_possible_duplicates(c)[0][2], "same street")

    def test_at_most_three_flags_and_best_first(self):
        for i in range(5):
            self.make(title=POTHOLE_A[0], description=POTHOLE_A[1] + f" number {i}", hours_ago=4)
        found = find_possible_duplicates(self.newer())
        self.assertEqual(len(found), 3)
        self.assertEqual([s for _, s, _ in found], sorted((s for _, s, _ in found), reverse=True))

    def test_unusable_text_and_errors_never_raise(self):
        c = self.newer(title="1234 5678", description="9999 0000 !!!!")
        self.assertEqual(find_possible_duplicates(c), [])
        from unittest import mock
        with mock.patch("complaints.services.duplicates.find_possible_duplicates", side_effect=RuntimeError("boom")):
            self.assertEqual(flag_possible_duplicates(self.newer()), 0)

    def test_database_rules(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DuplicateFlag.objects.create(complaint=self.older, possible_duplicate_of=self.older, similarity=0.9, reason="x")
        c = self.newer()
        DuplicateFlag.objects.create(complaint=c, possible_duplicate_of=self.older, similarity=0.9, reason="x")
        with self.assertRaises(IntegrityError), transaction.atomic():
            DuplicateFlag.objects.create(complaint=c, possible_duplicate_of=self.older, similarity=0.8, reason="x")
        with self.assertRaises(IntegrityError), transaction.atomic():
            DuplicateFlag.objects.create(complaint=self.older, possible_duplicate_of=c, similarity=1.5, reason="x")

    def test_routing_flags_duplicates_automatically(self):
        from complaints.services import route_complaint
        c = self.newer(status=S.SUBMITTED, dept=None)
        route_complaint(c)
        self.assertEqual(DuplicateFlag.objects.filter(complaint=c).count(), 1)


class ReviewTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.complaint.delete()
        self.older = self.make(title=POTHOLE_A[0], description=POTHOLE_A[1], hours_ago=5)
        self.new = self.make(title=POTHOLE_B[0], description=POTHOLE_B[1], hours_ago=1)
        flag_possible_duplicates(self.new)
        self.flag = DuplicateFlag.objects.get()

    def test_dismiss_changes_nothing_else(self):
        msg = review_duplicate(self.flag, actor=self.officer, is_duplicate=False)
        self.flag.refresh_from_db()
        self.new.refresh_from_db()
        self.assertEqual((self.flag.status, self.flag.reviewed_by, self.new.status), (DuplicateStatus.DISMISSED, self.officer, S.PENDING))
        self.assertIn("not a duplicate", msg)
        self.assertTrue(AuditLog.objects.filter(action="DUPLICATE_DISMISSED").exists())

    def test_confirming_closes_the_newer_complaint_and_tells_the_citizen(self):
        msg = review_duplicate(self.flag, actor=self.officer, is_duplicate=True)
        self.new.refresh_from_db()
        self.older.refresh_from_db()
        self.assertEqual((self.new.status, self.older.status), (S.REJECTED, S.PENDING))     # the original is untouched
        self.assertIn(self.older.reference, self.new.remarks.get().text)
        self.assertEqual(self.new.remarks.get().visibility, "PUBLIC")
        self.assertTrue(Notification.objects.filter(recipient=self.citizen, kind="REJECTED").exists())
        self.assertIn("closed as a duplicate", msg)
        self.assertTrue(AuditLog.objects.filter(action="DUPLICATE_CONFIRMED").exists())

    def test_confirming_after_work_started_only_records_the_link(self):
        Complaint.objects.filter(pk=self.new.pk).update(status=S.IN_PROGRESS)
        msg = review_duplicate(self.flag, actor=self.officer, is_duplicate=True)
        self.new.refresh_from_db()
        self.assertEqual(self.new.status, S.IN_PROGRESS)
        self.assertIn("left open", msg)

    def test_a_flag_can_only_be_decided_once(self):
        review_duplicate(self.flag, actor=self.officer, is_duplicate=False)
        with self.assertRaisesMessage(WorkflowError, "already been reviewed"):
            review_duplicate(self.flag, actor=self.officer, is_duplicate=True)

    def test_officer_screen_shows_panel_badge_and_filter(self):
        self.as_officer()
        page = self.client.get(reverse("officer:detail", args=[self.new.pk])).content.decode()
        for expected in ("Possible duplicates", self.older.reference, "same street", "Mark as duplicate", "Not a duplicate", "nothing is merged automatically"):
            self.assertIn(expected, page)
        self.assertIn("Newer complaints that may repeat this one", self.client.get(reverse("officer:detail", args=[self.older.pk])).content.decode())
        dash = self.client.get(reverse("officer:dashboard"))
        self.assertContains(dash, "Possible duplicate")
        self.assertEqual([c.pk for c in self.client.get(reverse("officer:dashboard"), {"duplicates": "on"}).context["complaints"]], [self.new.pk])

    def test_officer_decides_through_the_page(self):
        self.as_officer()
        url = reverse("officer:duplicate_review", args=[self.new.pk, self.flag.pk])
        self.client.post(url, {"decision": "maybe"})
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.status, DuplicateStatus.PENDING)
        response = self.client.post(url, {"decision": "duplicate"}, follow=True)
        self.assertContains(response, "closed as a duplicate")
        self.assertEqual(Complaint.objects.get(pk=self.new.pk).status, S.REJECTED)
        self.assertContains(self.client.post(url, {"decision": "duplicate"}, follow=True), "already been reviewed")

    def test_other_departments_and_roles_cannot_decide(self):
        url = reverse("officer:duplicate_review", args=[self.new.pk, self.flag.pk])
        self.client.force_login(self.water_officer)
        self.assertEqual(self.client.post(url, {"decision": "duplicate"}).status_code, 404)
        for user in (self.citizen, self.worker):
            self.client.force_login(user)
            self.assertEqual(self.client.post(url, {"decision": "duplicate"}).status_code, 403)
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.status, DuplicateStatus.PENDING)

    def test_another_departments_complaint_is_not_revealed(self):
        Complaint.objects.filter(pk=self.older.pk).update(department=self.water, title="Secret water matter")
        self.as_officer()
        page = self.client.get(reverse("officer:detail", args=[self.new.pk])).content.decode()
        self.assertIn("an earlier complaint handled by another department", page)
        self.assertNotIn("Secret water matter", page)
        self.assertNotIn(self.older.reference, page)

    def test_administrator_can_review_and_sees_everything(self):
        admin = make_user("admin@example.com", Role.ADMIN)
        self.client.force_login(admin)
        page = self.client.get(reverse("adminpanel:complaint", args=[self.new.pk])).content.decode()
        self.assertIn(self.older.reference, page)
        url = reverse("adminpanel:duplicate_review", args=[self.new.pk, self.flag.pk])
        self.assertContains(self.client.post(url, {"decision": "not_duplicate"}, follow=True), "Marked as not a duplicate")
        self.assertEqual(self.client.get(reverse("adminpanel:duplicate_review", args=[self.new.pk, self.flag.pk])).status_code, 405)

    def test_flag_must_belong_to_the_complaint_in_the_url(self):
        other = self.make(title="Unrelated complaint here")
        self.as_officer()
        self.assertEqual(self.client.post(reverse("officer:duplicate_review", args=[other.pk, self.flag.pk]), {"decision": "duplicate"}).status_code, 404)
