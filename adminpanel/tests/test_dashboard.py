from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from adminpanel import analytics
from complaints.models import Complaint, ComplaintStatus as S, Feedback
from ml_engine.models import MLModel

from .helpers import AdminTestCase


class DashboardNumbersTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        Complaint.objects.filter(pk=self.complaint.pk).delete()
        self.make(status=S.PENDING)
        self.make(status=S.DEPARTMENT_ASSIGNED)
        self.make(status=S.IN_PROGRESS, hours_ago=30, sla_hours=24)                 # overdue
        self.make(status=S.ASSIGNED_TO_WORKER)
        self.make(status=S.RESOLVED)
        self.make(status=S.CLOSED)
        self.make(dept=self.water, status=S.PENDING)
        self.waiting()
        Complaint.objects.filter(status=S.IN_PROGRESS).update(escalation_level=1)

    def test_summary_counts(self):
        s = analytics.summary_counts()
        self.assertEqual(s, {"total": 8, "pending": 3, "in_progress": 2, "resolved": 2, "overdue": 1, "escalated": 1, "needs_verification": 1})

    def test_by_department_by_area_and_status(self):
        self.assertEqual([(b["label"], b["value"]) for b in analytics.by_department()], [("Electricity", 6), ("Water Supply", 1)])
        self.assertEqual(analytics.by_department()[0]["percent"], 100)
        self.assertEqual(analytics.by_area()[0], {"label": "Jayanagar", "value": 8, "percent": 100})
        statuses = {b["label"]: b["value"] for b in analytics.status_distribution()}
        self.assertEqual(statuses["Pending"], 2)
        self.assertEqual(statuses["Needs verification"], 1)
        self.assertEqual(analytics.by_ward()[0]["label"], "Jayanagar, Ward 154")

    def test_priority_distribution_lists_all_levels(self):
        self.assertEqual([b["label"] for b in analytics.priority_distribution()], ["Critical", "High", "Medium", "Low"])

    def test_over_time_buckets_by_local_day(self):
        Complaint.objects.update(created_at=timezone.now() - timedelta(days=3))
        Complaint.objects.filter(status=S.CLOSED).update(created_at=timezone.now() - timedelta(days=60))     # outside the window
        data = analytics.over_time(30)
        self.assertEqual(len(data["series"]), 30)
        self.assertEqual(data["total"], 7)
        self.assertEqual(data["peak"][1], 7)
        self.assertTrue(data["points"].count(",") >= 30)

    def test_resolution_time_is_averaged_per_department(self):
        now = timezone.now()
        for hours in (10, 20):
            c = self.make(status=S.RESOLVED, hours_ago=hours)
            Complaint.objects.filter(pk=c.pk).update(resolved_at=now)
        self.assertEqual(analytics.resolution_time_by_department(), [{"label": "Electricity", "value": 15.0, "percent": 100}])

    def test_feedback_summary(self):
        done = [self.make(status=S.CLOSED) for _ in range(3)]
        for c, rating in zip(done, (5, 4, 1)):
            Feedback.objects.create(complaint=c, rating=rating, comment="x" if rating == 1 else "")
        f = analytics.feedback_summary()
        self.assertEqual((f["average"], f["count"]), (3.33, 3))
        self.assertEqual({b["label"]: b["value"] for b in f["distribution"]}["5 stars"], 1)
        self.assertEqual(f["by_department"], [{"name": "Electricity", "average": 3.33, "count": 3}])
        self.assertEqual(len(f["low"]), 1)

    def test_page_renders_all_sections_with_the_numbers(self):
        self.as_admin()
        page = self.client.get(reverse("adminpanel:dashboard")).content.decode()
        for expected in ("Total complaints", "By department", "By area", "Busiest wards", "By status", "By priority",
                         "Average hours to resolve", "Citizen feedback", "No AI model is active", "Needs verification"):
            self.assertIn(expected, page)
        self.assertIn('<svg viewBox="0 0 640 120"', page)


class DashboardAiSectionTests(AdminTestCase):
    def test_empty_database_renders(self):
        Complaint.objects.all().delete()
        self.as_admin()
        self.assertEqual(self.client.get(reverse("adminpanel:dashboard")).status_code, 200)

    def test_active_model_metrics_and_matrix_are_shown(self):
        MLModel.objects.create(
            version=2, artefact_file="x", artefact_sha256="0" * 64, labels=["ELECTRICITY", "ROADS"], dataset_size=100, train_size=80,
            test_size=20, class_distribution={}, accuracy=0.95, precision_macro=0.94, recall_macro=0.93, f1_macro=0.92,
            per_class_metrics={}, confusion_matrix=[[9, 1], [0, 10]], challenge_accuracy=0.8, best_params={}, cv_f1_macro=0.9,
            conf_threshold=0.6, threshold_analysis={}, is_active=True)
        self.as_admin()
        page = self.client.get(reverse("adminpanel:dashboard")).content.decode()
        for expected in ("95%", "94%", "93%", "92%", "Confusion matrix", "rp-miss", "80% accuracy", "0.6"):
            self.assertIn(expected, page)

    def test_production_correction_rate_is_computed_from_real_corrections(self):
        from complaints.models import RoutingCorrection
        a, b = self.make(), self.make()
        Complaint.objects.filter(pk__in=[a.pk, b.pk]).update(routing_method="AUTO")
        RoutingCorrection.objects.create(complaint=a, predicted_department=self.elec, corrected_department=self.water,
                                         corrected_by=self.admin, ai_was_correct=False, was_unrouted=False)
        ai = analytics.ai_overview()
        self.assertEqual((ai["auto_routed"], ai["corrected_after_routing"], ai["correction_rate"]), (2, 1, 50.0))
