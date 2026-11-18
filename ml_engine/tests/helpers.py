import shutil
from io import StringIO
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from ml_engine.model_manager import clear_cache


class MLTestCase(TestCase):
    """Writes model artefacts to a temporary directory and clears the model cache around tests."""

    @classmethod
    def setUpClass(cls):
        cls._ml_dir = tempfile.mkdtemp()
        cls._override = override_settings(ML_MODELS_DIR=cls._ml_dir)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._ml_dir, ignore_errors=True)

    def setUp(self):
        clear_cache()

    @staticmethod
    def seed_departments():
        call_command("seed_master_data", stdout=StringIO())

    @staticmethod
    def import_synthetic():
        call_command("import_dataset", str(Path(settings.DATASETS_DIR) / "complaints_synthetic_v1.csv"),
                     "--source", "SYNTHETIC", "--dataset-version", "synthetic_v1", stdout=StringIO())
