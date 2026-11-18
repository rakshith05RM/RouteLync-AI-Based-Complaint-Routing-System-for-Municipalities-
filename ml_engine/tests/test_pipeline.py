import io
import json
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command

from departments.models import Department
from ml_engine.dataset import import_rows
from ml_engine.exceptions import ModelUnavailableError, TrainingError
from ml_engine.model_manager import clear_cache, get_active_model, models_dir, sha256_of
from ml_engine.models import MLModel, TrainingSample
from ml_engine.predict import predict
from ml_engine.train import train_and_evaluate

from .helpers import MLTestCase

STREETLIGHT = "The streetlight near the junction has not been working for three days and the road is very dark at night."


class TrainedModelTests(MLTestCase):
    """Trains ONE model for the whole class (about 8 seconds), then checks training and prediction."""

    @classmethod
    def setUpTestData(cls):
        cls.seed_departments()
        cls.import_synthetic()
        cls.result = train_and_evaluate(notes="test run", activate=True)
        cls.model = cls.result.ml_model

    # ---------------- training and evaluation
    def test_dataset_sizes_and_split(self):
        m = self.model
        self.assertEqual((m.dataset_size, m.train_size, m.test_size), (1200, 960, 240))
        self.assertEqual(m.class_distribution, {"ELECTRICITY": 300, "WATER_SUPPLY": 300, "SANITATION": 300, "ROADS": 300})
        self.assertEqual(m.labels, ["ELECTRICITY", "ROADS", "SANITATION", "WATER_SUPPLY"])

    def test_train_and_test_sets_are_disjoint(self):
        train, test = set(self.result.train_texts), set(self.result.test_texts)
        self.assertEqual(len(train), 960)
        self.assertEqual(len(test), 240)
        self.assertFalse(train & test)

    def test_challenge_set_never_used_for_training(self):
        trained_on = {TrainingSample.hash_text(t) for t in TrainingSample.objects.values_list("text", flat=True)}
        challenge = {TrainingSample.hash_text(t) for t in self.result.challenge_texts}
        self.assertEqual(len(challenge), 64)
        self.assertFalse(trained_on & challenge)

    def test_metrics_generated_and_consistent(self):
        m = self.model
        for value in (m.accuracy, m.precision_macro, m.recall_macro, m.f1_macro, m.cv_f1_macro):
            self.assertTrue(0.0 <= value <= 1.0)
        self.assertGreaterEqual(m.accuracy, 0.95)            # synthetic split: optimistic by construction
        self.assertEqual(set(m.per_class_metrics), set(m.labels))
        self.assertEqual(sum(sum(row) for row in m.confusion_matrix), m.test_size)
        self.assertEqual(len(m.confusion_matrix), len(m.labels))

    def test_challenge_evaluation_is_reported_separately(self):
        m = self.model
        self.assertIsNotNone(m.challenge_accuracy)
        self.assertGreater(m.challenge_accuracy, 0.6)         # far above the 0.25 chance level
        self.assertEqual(set(m.challenge_report["by_difficulty"]), {"normal", "hard"})
        self.assertIsInstance(m.challenge_report["misclassified"], list)

    def test_threshold_is_data_driven_and_bounded(self):
        a = self.model.threshold_analysis
        self.assertGreaterEqual(self.model.conf_threshold, settings.ML_MIN_THRESHOLD)
        self.assertLessEqual(self.model.conf_threshold, 1.0)
        self.assertEqual(a["selected_threshold"], self.model.conf_threshold)
        self.assertEqual(len(a["out_of_fold_training"]), 5)

    def test_artefact_saved_with_checksum_and_metadata(self):
        path = models_dir() / self.model.artefact_file
        self.assertTrue(path.is_file())
        self.assertEqual(sha256_of(path), self.model.artefact_sha256)
        meta = json.loads((models_dir() / "model_v1.json").read_text())
        self.assertEqual(meta["dataset_size"], 1200)
        self.assertEqual(meta["random_state"], settings.ML_RANDOM_STATE)

    def test_only_one_model_is_active(self):
        self.assertTrue(MLModel.objects.get(pk=self.model.pk).is_active)
        second = MLModel.objects.get(pk=self.model.pk)
        second.pk, second.version, second.is_active = None, 2, False
        second.save()
        second.activate()
        self.assertEqual(list(MLModel.objects.filter(is_active=True)), [second])
        self.assertFalse(MLModel.objects.get(version=1).is_active)
        MLModel.objects.get(version=1).activate()            # restore for the other tests
        self.assertEqual(MLModel.objects.filter(is_active=True).count(), 1)

    # ---------------- prediction
    def test_prediction_returns_probabilities_and_department(self):
        p = predict(STREETLIGHT)
        self.assertEqual(p.department_code, "ELECTRICITY")
        self.assertAlmostEqual(sum(p.probabilities.values()), 1.0, places=6)
        self.assertEqual(max(p.probabilities, key=p.probabilities.get), "ELECTRICITY")
        self.assertEqual(p.confidence, p.probabilities["ELECTRICITY"])
        self.assertEqual((p.model_version, p.model_id), (1, self.model.pk))
        self.assertFalse(p.needs_verification)

    def test_each_department_is_predicted_for_a_typical_complaint(self):
        cases = {
            "There is a large pothole on the road near the bus stop causing accidents": "ROADS",
            "Garbage has not been collected from our street for a week": "SANITATION",
            "There is no water supply in our area since yesterday morning": "WATER_SUPPLY",
            "A live electric wire is hanging low near the transformer": "ELECTRICITY",
        }
        for text, expected in cases.items():
            self.assertEqual(predict(text).department_code, expected, text)

    def test_unusable_or_unknown_input_needs_verification(self):
        for text, reason in (("", "no_usable_text"), ("!!! 123 ???", "no_usable_text"),
                             ("asdf qwer zxcv", "no_known_terms"), ("quantum entanglement flux capacitor", "no_known_terms")):
            p = predict(text)
            self.assertTrue(p.needs_verification, text)
            self.assertEqual((p.reason, p.department_code, p.confidence), (reason, None, 0.0), text)

    def test_low_confidence_goes_to_verification_but_keeps_suggestion(self):
        p = predict(STREETLIGHT, threshold=1.01)
        self.assertTrue(p.needs_verification)
        self.assertEqual(p.reason, "low_confidence")
        self.assertEqual(p.department_code, "ELECTRICITY")     # suggestion shown to the admin

    def test_explanation_lists_influential_original_words(self):
        p = predict(STREETLIGHT)
        words = [t["term"] for t in p.top_terms]
        self.assertIn("streetlight", words)
        self.assertLessEqual(len(words), 5)
        self.assertTrue(all(t["score"] > 0 and 0 < t["share"] <= 1 for t in p.top_terms))
        self.assertEqual(p.top_terms, sorted(p.top_terms, key=lambda t: -t["score"]))

    def test_model_is_cached_between_calls(self):
        self.assertIs(get_active_model()[1], get_active_model()[1])

    # ---------------- integrity and failure handling
    def test_tampered_artefact_is_refused(self):
        path = models_dir() / self.model.artefact_file
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"tampered")
            clear_cache()
            with self.assertRaisesMessage(ModelUnavailableError, "integrity"):
                predict(STREETLIGHT)
        finally:
            path.write_bytes(original)
            clear_cache()
        self.assertEqual(predict(STREETLIGHT).department_code, "ELECTRICITY")

    def test_missing_artefact_is_reported(self):
        path = models_dir() / self.model.artefact_file
        original = path.read_bytes()
        try:
            path.unlink()
            clear_cache()
            with self.assertRaisesMessage(ModelUnavailableError, "missing"):
                predict(STREETLIGHT)
        finally:
            path.write_bytes(original)
            clear_cache()

    def test_predict_command_output(self):
        out = io.StringIO()
        call_command("predict_complaint", STREETLIGHT, stdout=out)
        text = out.getvalue()
        self.assertIn("Prediction   : ELECTRICITY", text)
        self.assertIn("auto-route", text)
        self.assertIn("streetlight", text)


class NoModelTests(MLTestCase):
    def test_predict_without_model_raises_clearly(self):
        with self.assertRaisesMessage(ModelUnavailableError, "No active ML model"):
            predict(STREETLIGHT)

    def test_inactive_model_is_not_used(self):
        self.seed_departments()
        self.import_synthetic()
        train_and_evaluate(activate=False)
        with self.assertRaises(ModelUnavailableError):
            predict(STREETLIGHT)


class TrainingGuardTests(MLTestCase):
    def setUp(self):
        super().setUp()
        self.seed_departments()

    def add(self, code, n, verified=True, start=0):
        dept = Department.objects.get(code=code)
        for i in range(n):
            TrainingSample.objects.create(
                department=dept, is_verified=verified,
                text=f"{code.lower()} complaint number {start + i} about a problem in our area")

    def test_no_samples(self):
        with self.assertRaisesMessage(TrainingError, "no verified"):
            train_and_evaluate()

    def test_single_class_refused(self):
        self.add("ROADS", 40)
        with self.assertRaisesMessage(TrainingError, "at least two"):
            train_and_evaluate()

    def test_tiny_class_refused(self):
        self.add("ROADS", 40)
        self.add("WATER_SUPPLY", 5)
        with self.assertRaisesMessage(TrainingError, "Too few samples"):
            train_and_evaluate()

    def test_unverified_samples_are_never_trained_on(self):
        self.add("ROADS", 30)
        self.add("WATER_SUPPLY", 30)
        self.add("SANITATION", 100, verified=False)         # many rows, but not verified
        from ml_engine.train import load_training_data
        _, labels, counts = load_training_data()
        self.assertEqual(set(counts), {"ROADS", "WATER_SUPPLY"})
        self.assertNotIn("SANITATION", labels)
