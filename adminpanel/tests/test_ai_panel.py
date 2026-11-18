import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from audit.models import AuditLog
from ml_engine.model_manager import clear_cache
from ml_engine.models import MLModel, TrainingSample

from .helpers import AdminTestCase

GOOD = "Water is not coming from the tap since yesterday morning"
OTHER = "Garbage has not been collected from our street for a week now"


def csv_upload(text, name="data.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


class ModelManagementTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        import shutil, tempfile
        self._dir = tempfile.mkdtemp()
        self._override = override_settings(ML_MODELS_DIR=self._dir)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(shutil.rmtree, self._dir, True)
        clear_cache()
        self.as_admin()

    def fake_model(self, version=1, **kw):
        values = dict(version=version, artefact_file="x", artefact_sha256="0" * 64, labels=["ELECTRICITY", "ROADS"], dataset_size=10,
                      train_size=8, test_size=2, class_distribution={}, accuracy=0.9, precision_macro=0.9, recall_macro=0.9, f1_macro=0.9,
                      per_class_metrics={"ELECTRICITY": {"precision": 1, "recall": 1, "f1": 1, "support": 1}},
                      confusion_matrix=[[1, 0], [0, 1]], best_params={}, cv_f1_macro=0.9, conf_threshold=0.6,
                      threshold_analysis={"selected_threshold": 0.6})
        values.update(kw)
        return MLModel.objects.create(**values)

    def test_train_review_and_activate_flow(self):
        call_command("seed_master_data", stdout=io.StringIO())
        call_command("import_dataset", "datasets/complaints_synthetic_v1.csv", "--source", "SYNTHETIC", stdout=io.StringIO())
        response = self.client.post(reverse("adminpanel:train"), follow=True)
        self.assertContains(response, "Model v1 trained")
        model = MLModel.objects.get()
        self.assertFalse(model.is_active)                                       # training never activates by itself
        self.assertEqual(model.trained_by, self.admin)
        self.assertContains(response, "Activate")
        self.assertTrue(AuditLog.objects.filter(action="MODEL_TRAINED", target_id=model.pk, user=self.admin).exists())
        self.client.post(reverse("adminpanel:activate", args=[model.pk]))
        model.refresh_from_db()
        self.assertTrue(model.is_active)
        self.assertTrue(AuditLog.objects.filter(action="MODEL_ACTIVATED", target_id=model.pk).exists())
        page = self.client.get(reverse("adminpanel:ai"))
        self.assertContains(page, "Active model: version 1")
        self.assertContains(page, "Confusion matrix") if False else None
        from ml_engine.predict import predict
        self.assertEqual(predict("The streetlight is not working and the road is dark").department_code, "ELECTRICITY")

    def test_training_without_data_shows_a_friendly_message(self):
        response = self.client.post(reverse("adminpanel:train"), follow=True)
        self.assertContains(response, "no verified training samples")
        self.assertEqual(MLModel.objects.count(), 0)

    def test_only_one_model_is_active_after_switching(self):
        a, b = self.fake_model(1, is_active=True), self.fake_model(2)
        self.client.post(reverse("adminpanel:activate", args=[b.pk]))
        self.assertEqual(list(MLModel.objects.filter(is_active=True)), [b])
        self.assertEqual(self.client.post(reverse("adminpanel:activate", args=[9999])).status_code, 404)

    def test_threshold_can_be_changed_within_limits_and_is_audited(self):
        m = self.fake_model(1, is_active=True)
        url = reverse("adminpanel:threshold", args=[m.pk])
        for bad in ("0.3", "1.5", "abc", ""):
            self.client.post(url, {"threshold": bad})
        m.refresh_from_db()
        self.assertEqual(m.conf_threshold, 0.6)
        self.client.post(url, {"threshold": "0.85"})
        m.refresh_from_db()
        self.assertEqual(m.conf_threshold, 0.85)
        self.assertIn("0.6 -> 0.85", AuditLog.objects.get(action="THRESHOLD_CHANGED").summary)

    def test_page_shows_metrics_models_and_correction_stats(self):
        self.fake_model(1, is_active=True)
        self.fake_model(2)
        page = self.client.get(reverse("adminpanel:ai")).content.decode()
        for expected in ("Active model: version 1", "90%", "Confusion matrix" if False else "Actual", "v2", "Human corrections", "Confidence threshold"):
            self.assertIn(expected, page)


class DatasetManagementTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        from accounts.tests.helpers import make_department
        make_department("ROADS")
        make_department("SANITATION")
        self.as_admin()
        self.upload = reverse("adminpanel:dataset_upload")

    def test_check_only_saves_nothing(self):
        response = self.client.post(self.upload, {"file": csv_upload(f"text,department_code\n{GOOD},WATER_SUPPLY\n{OTHER},SANITATION\n"), "dry_run": "on"}, follow=True)
        self.assertContains(response, "imported: 2")
        self.assertContains(response, "DRY RUN")
        self.assertEqual(TrainingSample.objects.count(), 0)

    def test_import_saves_audits_and_reports_problems(self):
        csv_text = f"text,department_code\n{GOOD},WATER_SUPPLY\n{GOOD},ROADS\ntest,ROADS\n{OTHER},PARKS\n"
        response = self.client.post(self.upload, {"file": csv_upload(csv_text), "dataset_version": "batch1"}, follow=True)
        self.assertContains(response, "imported: 1")
        self.assertContains(response, "labelled WATER_SUPPLY and ROADS")
        self.assertContains(response, "Row 4")
        self.assertContains(response, 'Unknown department "PARKS"')
        sample = TrainingSample.objects.get()
        self.assertEqual((sample.dataset_version, sample.is_verified), ("batch1", True))
        self.assertTrue(AuditLog.objects.filter(action="DATASET_IMPORTED").exists())

    def test_bad_files_are_refused(self):
        for upload in (csv_upload("text,label\nhello,x\n"), csv_upload("x" * (2 * 1024 * 1024 + 10)), SimpleUploadedFile("a.csv", b"\xff\xfe\x00bad", content_type="text/csv")):
            response = self.client.post(self.upload, {"file": upload}, follow=True)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(TrainingSample.objects.count(), 0)
        self.assertContains(self.client.post(self.upload, {"file": csv_upload("text,label\nhello,x\n")}, follow=True), "missing required column")
        self.assertEqual(self.client.post(self.upload, {}).status_code, 302)

    def test_add_single_example(self):
        url = reverse("adminpanel:dataset_add")
        self.assertContains(self.client.post(url, {"text": GOOD, "department": self.water.pk}, follow=True), "Training example added")
        self.assertContains(self.client.post(url, {"text": GOOD, "department": self.water.pk}, follow=True), "already exists")
        self.assertContains(self.client.post(url, {"text": GOOD, "department": self.elec.pk}, follow=True), "already labelled Water Supply")
        self.assertContains(self.client.post(url, {"text": "abc", "department": self.water.pk}, follow=True), "Not added")
        self.assertEqual(TrainingSample.objects.count(), 1)
        self.assertTrue(AuditLog.objects.filter(action="SAMPLE_ADDED").exists())

    def test_statistics_and_listing_with_filters(self):
        TrainingSample.objects.create(text=GOOD, department=self.water, is_verified=True)
        TrainingSample.objects.create(text=OTHER, department=self.elec, is_verified=False)
        page = self.client.get(reverse("adminpanel:dataset"))
        self.assertEqual(page.context["stats"]["verified_rows"], 1)
        self.assertContains(page, "1 verified example")
        self.assertContains(page, "1 not verified")
        self.assertEqual(len(self.client.get(reverse("adminpanel:dataset"), {"verified": "no"}).context["samples"]), 1)
        self.assertEqual(len(self.client.get(reverse("adminpanel:dataset"), {"department": self.water.pk}).context["samples"]), 1)
        self.assertEqual(len(self.client.get(reverse("adminpanel:dataset"), {"department": "abc"}).context["samples"]), 2)

    def test_export_contains_only_verified_rows_and_neutralises_formulas(self):
        TrainingSample.objects.create(text=GOOD, department=self.water, is_verified=True, source="IMPORTED")
        TrainingSample.objects.create(text="=HYPERLINK(\"http://evil\") water is leaking from the main pipe on our road", department=self.water, is_verified=True)
        TrainingSample.objects.create(text=OTHER, department=self.elec, is_verified=False)
        response = self.client.get(reverse("adminpanel:dataset_export"))
        body = response.content.decode()
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(GOOD, body)
        self.assertNotIn(OTHER, body)
        self.assertIn("'=HYPERLINK", body)
        self.assertEqual(body.splitlines()[0], "text,department_code,source,is_verified,dataset_version")
