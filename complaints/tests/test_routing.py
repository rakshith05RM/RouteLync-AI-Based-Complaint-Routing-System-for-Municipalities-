import io
import shutil
import tempfile
from unittest import mock

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.forms import ComplaintForm
from complaints.models import Complaint, ComplaintStatus as S, RoutingMethod
from complaints.selectors import complaints_visible_to
from complaints.services import RoutingError, manual_route, route_complaint, submit_complaint
from departments.models import Department, Priority
from ml_engine.exceptions import ModelUnavailableError
from ml_engine.model_manager import clear_cache
from ml_engine.models import MLModel
from ml_engine.train import train_and_evaluate

from .helpers import ComplaintTestCase

STREETLIGHT = "The streetlight near the junction has not been working for three days and the road is very dark at night."


class RoutingBase(ComplaintTestCase):
    @classmethod
    def setUpClass(cls):
        cls._ml_dir = tempfile.mkdtemp()
        cls._ml_override = override_settings(ML_MODELS_DIR=cls._ml_dir)
        cls._ml_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._ml_override.disable()
        shutil.rmtree(cls._ml_dir, ignore_errors=True)

    def setUp(self):
        super().setUp()
        clear_cache()

    def make_complaint(self, title="Streetlight not working near junction", description=STREETLIGHT, user=None):
        user = user or self.citizen
        data, files = self.form_args(title=title, description=description)
        form = ComplaintForm(data, files, citizen=user)
        assert form.is_valid(), form.errors
        return submit_complaint(citizen=user, data=form.cleaned_data, image=form.cleaned_data["image"])

    def history(self, complaint):
        return list(complaint.status_history.values_list("to_status", flat=True))


class RoutingWithModelTests(RoutingBase):
    """One trained model for the whole class (about 8 seconds)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_master_data", stdout=io.StringIO())
        call_command("import_dataset", "datasets/complaints_synthetic_v1.csv", "--source", "SYNTHETIC", stdout=io.StringIO())
        cls.model = train_and_evaluate(activate=True).ml_model

    def test_confident_complaint_is_auto_routed_to_the_right_department(self):
        c = self.make_complaint()
        outcome = route_complaint(c)
        c.refresh_from_db()
        self.assertTrue(outcome.auto_routed)
        self.assertEqual((c.status, c.department.code, c.routing_method), (S.PENDING, "ELECTRICITY", RoutingMethod.AUTO))
        self.assertEqual(c.predicted_department, c.department)
        self.assertEqual(self.history(c), ["SUBMITTED", "AI_PROCESSING", "DEPARTMENT_ASSIGNED", "PENDING"])
        self.assertIsNotNone(c.routed_at)
        self.assertEqual(c.routing_reason, "")

    def test_prediction_details_are_stored(self):
        c = self.make_complaint()
        route_complaint(c)
        c.refresh_from_db()
        self.assertEqual(c.ai_model, self.model)
        self.assertAlmostEqual(sum(c.ai_probabilities.values()), 1.0, places=6)
        self.assertAlmostEqual(c.ai_confidence, c.ai_probabilities["ELECTRICITY"], places=12)   # DOUBLE and JSON can differ in the last digit on MySQL
        self.assertTrue(0.0 <= c.ai_confidence <= 1.0)
        self.assertIsNotNone(c.ai_predicted_at)
        self.assertTrue(c.cleaned_text)
        self.assertIn("streetlight", [t["term"] for t in c.ai_terms])
        note = c.status_history.get(to_status="DEPARTMENT_ASSIGNED").note
        self.assertIn("Electricity", note)
        self.assertIn("model v1", note)

    def test_each_department_receives_its_own_complaints(self):
        cases = [
            ("Large pothole on the road", "There is a large pothole on the road near the bus stop causing trouble to riders", "ROADS"),
            ("Garbage not collected", "Garbage has not been collected from our street for a week now", "SANITATION"),
            ("No water supply", "There is no water supply in our area since yesterday morning", "WATER_SUPPLY"),
            ("Streetlight not working", STREETLIGHT, "ELECTRICITY"),
        ]
        for title, text, code in cases:
            c = self.make_complaint(title=title, description=text)
            route_complaint(c)
            self.assertEqual(c.department.code, code, text)

    def test_priority_and_sla_are_set_from_rules(self):
        c = self.make_complaint(title="Live wire hanging", description="A live electric wire is hanging low near the transformer in our lane")
        route_complaint(c)
        self.assertEqual((c.priority, c.priority_reason), (Priority.CRITICAL, "Live or hanging electric wire"))
        self.assertEqual((c.sla_deadline - c.created_at).total_seconds(), 4 * 3600)
        m = self.make_complaint()
        route_complaint(m)
        self.assertEqual(m.priority, Priority.MEDIUM)
        self.assertEqual((m.sla_deadline - m.created_at).total_seconds(), 24 * 3600)
        self.assertFalse(m.sla_state().is_overdue)

    def test_low_confidence_goes_to_verification_with_suggestion_kept(self):
        MLModel.objects.filter(pk=self.model.pk).update(conf_threshold=1.01)
        c = self.make_complaint()
        outcome = route_complaint(c)
        c.refresh_from_db()
        self.assertFalse(outcome.auto_routed)
        self.assertEqual((c.status, c.department, c.routing_reason), (S.NEEDS_VERIFICATION, None, "low_confidence"))
        self.assertEqual(c.predicted_department.code, "ELECTRICITY")
        self.assertEqual(self.history(c), ["SUBMITTED", "AI_PROCESSING", "NEEDS_VERIFICATION"])
        self.assertIsNotNone(c.sla_deadline)                  # the SLA clock runs from submission regardless
        MLModel.objects.filter(pk=self.model.pk).update(conf_threshold=self.model.conf_threshold)

    def test_text_the_classifier_cannot_read_is_sent_to_a_person_not_guessed(self):
        # A complaint in Kannada passes the description check (the rules and the model are English-only), so it is
        # ACCEPTED and then routed to a human instead of being forced into a department.
        c = self.make_complaint(title="ಬೀದಿ ದೀಪ ಸಮಸ್ಯೆ", description="ರಸ್ತೆಯ ಬೀದಿ ದೀಪ ಮೂರು ದಿನಗಳಿಂದ ಕೆಲಸ ಮಾಡುತ್ತಿಲ್ಲ ದಯವಿಟ್ಟು ಸರಿಪಡಿಸಿ")
        route_complaint(c)
        self.assertEqual((c.status, c.department, c.predicted_department, c.routing_reason),
                         (S.NEEDS_VERIFICATION, None, None, "no_usable_text"))
        self.assertIsNone(c.ai_confidence)

    def test_inactive_predicted_department_needs_verification(self):
        Department.objects.filter(code="ELECTRICITY").update(is_active=False)
        c = self.make_complaint()
        route_complaint(c)
        self.assertEqual((c.status, c.department, c.routing_reason), (S.NEEDS_VERIFICATION, None, "department_unavailable"))
        self.assertEqual(c.predicted_department.code, "ELECTRICITY")

    def test_unexpected_model_error_degrades_to_manual_verification(self):
        c = self.make_complaint()
        with mock.patch("complaints.services.routing.predict", side_effect=RuntimeError("boom")):
            route_complaint(c)
        self.assertEqual((c.status, c.routing_reason), (S.NEEDS_VERIFICATION, "error"))
        self.assertTrue(c.priority_reason)                    # rules still ran

    def test_a_complaint_cannot_be_routed_twice(self):
        c = self.make_complaint()
        route_complaint(c)
        with self.assertRaises(RoutingError):
            route_complaint(c)
        self.assertEqual(self.history(c).count("AI_PROCESSING"), 1)

    def test_routing_is_atomic(self):
        c = self.make_complaint()
        with mock.patch("complaints.services.routing.transition_complaint",
                        side_effect=[c, RuntimeError("db down")]):
            with self.assertRaises(RuntimeError):
                route_complaint(c)
        c.refresh_from_db()
        self.assertEqual(c.status, S.SUBMITTED)

    def test_officers_see_only_their_departments_complaints(self):
        c = self.make_complaint()
        route_complaint(c)
        elec = make_user("e@example.com", Role.OFFICER, department=Department.objects.get(code="ELECTRICITY"))
        water = make_user("w@example.com", Role.OFFICER, department=Department.objects.get(code="WATER_SUPPLY"))
        self.assertEqual(list(complaints_visible_to(elec)), [c])
        self.assertEqual(list(complaints_visible_to(water)), [])

    def test_unrouted_complaint_is_invisible_to_officers(self):
        c = self.make_complaint()                              # still SUBMITTED, department NULL
        elec = make_user("e@example.com", Role.OFFICER, department=Department.objects.get(code="ELECTRICITY"))
        self.assertNotIn(c, complaints_visible_to(elec))

    # ---- through the real web form
    def test_submission_through_the_form_routes_and_citizen_sees_safe_view(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("complaints:new"), self.payload())
        c = Complaint.objects.get()
        self.assertRedirects(response, reverse("complaints:detail", args=[c.pk]))
        self.assertEqual((c.status, c.department.code), (S.PENDING, "ELECTRICITY"))
        page = self.client.get(reverse("complaints:detail", args=[c.pk])).content.decode()
        self.assertIn("Electricity", page)
        self.assertIn("Sent to department", page)
        for internal in ("AI processing", "Needs verification", "confidence", "Critical", "priority", "model"):
            self.assertNotIn(internal, page)
        self.assertEqual(page.count("Sent to department"), 2)  # badge + one timeline step (duplicates folded)

    def test_citizen_never_sees_internal_review_wording(self):
        MLModel.objects.filter(pk=self.model.pk).update(conf_threshold=1.01)
        self.client.force_login(self.citizen)
        self.client.post(reverse("complaints:new"), self.payload())
        c = Complaint.objects.get()
        self.assertEqual(c.status, S.NEEDS_VERIFICATION)
        page = self.client.get(reverse("complaints:detail", args=[c.pk])).content.decode()
        self.assertIn("Under review", page)
        self.assertNotIn("Needs verification", page)
        MLModel.objects.filter(pk=self.model.pk).update(conf_threshold=self.model.conf_threshold)

    # ---- human in the loop
    def test_administrator_routes_a_waiting_complaint(self):
        MLModel.objects.filter(pk=self.model.pk).update(conf_threshold=1.01)
        c = self.make_complaint()
        route_complaint(c)
        MLModel.objects.filter(pk=self.model.pk).update(conf_threshold=self.model.conf_threshold)
        admin = make_user("admin@example.com", Role.ADMIN)
        manual_route(c, Department.objects.get(code="ROADS"), actor=admin)
        c.refresh_from_db()
        self.assertEqual((c.status, c.department.code, c.routing_method), (S.PENDING, "ROADS", RoutingMethod.MANUAL))
        self.assertEqual(c.predicted_department.code, "ELECTRICITY")        # the AI's original suggestion is preserved
        last = c.status_history.filter(to_status="DEPARTMENT_ASSIGNED").get()
        self.assertEqual(last.changed_by, admin)

    def test_manual_route_rejects_wrong_state_and_inactive_department(self):
        c = self.make_complaint()
        route_complaint(c)                                                   # now PENDING
        admin = make_user("admin@example.com", Role.ADMIN)
        from complaints.services import InvalidTransition
        with self.assertRaises(InvalidTransition):
            manual_route(c, Department.objects.get(code="ROADS"), actor=admin)
        Department.objects.filter(code="ROADS").update(is_active=False)
        with self.assertRaises(RoutingError):
            manual_route(c, Department.objects.get(code="ROADS"), actor=admin)

    def test_route_pending_command_processes_stuck_complaints(self):
        stuck = [self.make_complaint(), self.make_complaint(description="Garbage has not been collected from our street for a week")]
        out = io.StringIO()
        call_command("route_pending_complaints", stdout=out)
        self.assertIn("routed=2 failed=0", out.getvalue())
        for c in stuck:
            c.refresh_from_db()
            self.assertEqual(c.status, S.PENDING)


class RoutingWithoutModelTests(RoutingBase):
    def test_no_model_complaint_is_kept_and_sent_to_verification(self):
        c = self.make_complaint()
        outcome = route_complaint(c)
        c.refresh_from_db()
        self.assertFalse(outcome.auto_routed)
        self.assertEqual((c.status, c.routing_reason, c.department), (S.NEEDS_VERIFICATION, "model_unavailable", None))
        self.assertIsNone(c.ai_confidence)
        self.assertEqual(c.priority, Priority.MEDIUM)         # rule-based priority and SLA still work without the model
        self.assertIsNotNone(c.sla_deadline)

    def test_form_submission_succeeds_even_if_routing_crashes(self):
        self.client.force_login(self.citizen)
        with mock.patch("complaints.views.citizen.route_complaint", side_effect=RuntimeError("boom")):
            response = self.client.post(reverse("complaints:new"), self.payload())
        c = Complaint.objects.get()
        self.assertRedirects(response, reverse("complaints:detail", args=[c.pk]))
        self.assertEqual(c.status, S.SUBMITTED)                # saved; route_pending_complaints can finish the job
        call_command("route_pending_complaints", stdout=io.StringIO())
        c.refresh_from_db()
        self.assertEqual(c.status, S.NEEDS_VERIFICATION)
