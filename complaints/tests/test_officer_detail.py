from django.urls import reverse

from complaints.models import ComplaintImage, ComplaintStatus as S, ComplaintStatusHistory, RoutingMethod
from complaints.services.submission import sanitize_image
from ml_engine.models import MLModel

from .helpers import make_upload
from .officer_helpers import OfficerTestCase


class OfficerDetailTests(OfficerTestCase):
    def setUp(self):
        super().setUp()
        self.login_officer()

    def ai_model(self):
        return MLModel.objects.create(
            version=3, artefact_file="x.joblib", artefact_sha256="0" * 64, labels=["ELECTRICITY", "ROADS"],
            dataset_size=10, train_size=8, test_size=2, class_distribution={}, accuracy=1, precision_macro=1,
            recall_macro=1, f1_macro=1, per_class_metrics={}, confusion_matrix=[], best_params={}, cv_f1_macro=1,
            conf_threshold=0.5, threshold_analysis={})

    def test_page_shows_complaint_location_citizen_and_sla(self):
        c = self.make(title="Streetlight not working", description="The light is off since three days", landmark="Near Metro",
                      hours_ago=30, sla_hours=24, priority="HIGH", lat=12.925012, lng=77.5938)
        c.priority_reason = "Accidents or injury risk"
        c.save()
        page = self.client.get(reverse("officer:detail", args=[c.pk])).content.decode()
        for expected in (c.reference, "Streetlight not working", "The light is off since three days", "Jayanagar, Ward 154",
                         "4th Main Road", "Near Metro", "12.925012, 77.593800", "High", "Accidents or injury risk",
                         "Overdue by 6 h", self.citizen.full_name, "Electricity", 'id="complaint-map"'):
            self.assertIn(expected, page)
        self.assertNotIn(self.citizen.email, page)                 # contact email is not needed by officers

    def test_ai_panel_shows_prediction_details(self):
        model = self.ai_model()
        c = self.make()
        c.ai_model, c.predicted_department, c.ai_confidence = model, self.elec, 0.912
        c.ai_probabilities = {"ELECTRICITY": 0.912, "ROADS": 0.088}
        c.ai_terms = [{"term": "streetlight", "score": 3.1, "share": 0.6}, {"term": "dark", "score": 1.2, "share": 0.4}]
        c.routing_method = RoutingMethod.AUTO
        c.ai_predicted_at = c.created_at
        c.save()
        page = self.client.get(reverse("officer:detail", args=[c.pk])).content.decode()
        for expected in ("Predicted department", "91%", "Version 3", "Automatic (AI)", "91.2%", "8.8%", "streetlight",
                         "Influential terms", "next most likely department"):
            self.assertIn(expected, page)

    def test_manual_routing_is_explained(self):
        model = self.ai_model()
        c = self.make()
        c.ai_model, c.predicted_department, c.ai_confidence = model, self.water, 0.55
        c.routing_method = RoutingMethod.MANUAL
        c.ai_predicted_at = c.created_at
        c.save()
        page = self.client.get(reverse("officer:detail", args=[c.pk])).content.decode()
        self.assertIn("The model suggested Water Supply; an administrator routed this complaint to Electricity", page)

    def test_complaint_without_ai_data(self):
        c = self.make()
        c.ai_confidence = None
        c.save()
        self.assertContains(self.client.get(reverse("officer:detail", args=[c.pk])), "No AI prediction was recorded")

    def test_history_evidence_and_no_map_without_gps(self):
        c = self.make()
        ComplaintStatusHistory.objects.create(complaint=c, from_status="", to_status=S.SUBMITTED, changed_by=self.citizen, note="Complaint submitted")
        ComplaintStatusHistory.objects.create(complaint=c, from_status="SUBMITTED", to_status=S.AI_PROCESSING, note="AI analysis started")
        image = ComplaintImage.objects.create(complaint=c, image=sanitize_image(make_upload()))
        page = self.client.get(reverse("officer:detail", args=[c.pk])).content.decode()
        self.assertIn("AI processing", page)                      # staff see internal steps
        self.assertIn("System", page)
        self.assertIn(self.citizen.full_name, page)
        self.assertIn(reverse("complaints:image", args=[c.pk, image.pk]), page)
        self.assertNotIn('id="complaint-map"', page)

    def test_resolved_complaint_shows_no_sla_countdown(self):
        c = self.make(status=S.RESOLVED, hours_ago=50)
        page = self.client.get(reverse("officer:detail", args=[c.pk])).content.decode()
        self.assertNotIn("Overdue by", page)
