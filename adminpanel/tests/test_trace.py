import io

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from ml_engine.model_manager import clear_cache
from ml_engine.train import train_and_evaluate

from .helpers import AdminTestCase


class ModelTraceTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        import shutil, tempfile
        d = tempfile.mkdtemp()
        o = override_settings(ML_MODELS_DIR=d)
        o.enable()
        self.addCleanup(o.disable)
        self.addCleanup(shutil.rmtree, d, True)
        clear_cache()
        self.as_admin()
        self.url = reverse("adminpanel:trace")

    def test_without_a_model_the_page_explains(self):
        response = self.client.post(self.url, {"text": "No water supply since yesterday"}, follow=True)
        self.assertContains(response, "No active ML model")

    def test_blank_text_is_refused(self):
        self.assertContains(self.client.post(self.url, {"text": "   "}, follow=True), "Type some text")

    def test_every_stage_is_shown(self):
        call_command("seed_master_data", stdout=io.StringIO())
        call_command("import_dataset", "datasets/complaints_synthetic_v1.csv", "--source", "SYNTHETIC", stdout=io.StringIO())
        train_and_evaluate(activate=True)
        page = self.client.post(self.url, {"text": "The street-light isn't working near 4th Main since 3 days!"}).content.decode()
        for expected in ("Cleaning", "Tokens", "Stop-words removed", "Stemming", "TF-IDF features", "Naive Bayes", "ELECTRICITY",
                         "streetlight", "not", "would be routed automatically", "Model version 1"):
            self.assertIn(expected, page)
        gibberish = self.client.post(self.url, {"text": "asdf qwer zxcv"}).content.decode()
        self.assertIn("verification queue", gibberish)
        self.assertEqual(self.client.get(self.url).status_code, 405)
