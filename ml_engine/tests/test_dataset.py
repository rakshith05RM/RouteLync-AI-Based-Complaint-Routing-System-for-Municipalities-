import csv
from io import StringIO
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from complaints.validators import validate_description
from departments.models import Department
from ml_engine.data_generation import ISSUES, generate
from ml_engine.dataset import import_rows, read_csv, statistics
from ml_engine.exceptions import DatasetError
from ml_engine.models import TrainingSample

GOOD = "Water is not coming from the tap since yesterday morning"


class GeneratorTests(SimpleTestCase):
    def test_deterministic_and_seed_sensitive(self):
        self.assertEqual(generate(20, seed=1), generate(20, seed=1))
        self.assertNotEqual(generate(20, seed=1), generate(20, seed=2))

    def test_balanced_unique_and_valid(self):
        rows = generate(300)
        counts = {}
        for r in rows:
            counts[r["department_code"]] = counts.get(r["department_code"], 0) + 1
        self.assertEqual(set(counts), set(ISSUES))
        self.assertEqual(set(counts.values()), {300})
        texts = [" ".join(r["text"].lower().split()) for r in rows]
        self.assertEqual(len(texts), len(set(texts)))
        for r in rows:
            validate_description(r["text"])          # synthetic data passes the same rules as citizen input
            self.assertEqual(r["source"], "SYNTHETIC")

    def test_challenge_set_is_separate_from_synthetic_data(self):
        challenge = read_csv(Path(settings.DATASETS_DIR) / "challenge_set.csv")
        self.assertEqual(len(challenge), 64)
        self.assertEqual({r["department_code"] for r in challenge}, set(ISSUES))
        hashes = lambda rows: {TrainingSample.hash_text(r["text"]) for r in rows}   # noqa: E731
        self.assertFalse(hashes(challenge) & hashes(generate(300)))
        self.assertFalse(hashes(challenge) & hashes(read_csv(Path(settings.DATASETS_DIR) / "complaints_synthetic_v1.csv")))


class ImportTests(TestCase):
    def setUp(self):
        call_command("seed_master_data", stdout=StringIO())

    def rows(self, *items):
        return [{"text": t, "department_code": c} for t, c in items]

    def test_valid_rows_imported_as_verified(self):
        report = import_rows(self.rows((GOOD, "WATER_SUPPLY"), ("Garbage has not been collected for a week now", "sanitation")))
        self.assertEqual((report.imported, report.rows_read), (2, 2))
        sample = TrainingSample.objects.get(department__code="WATER_SUPPLY")
        self.assertTrue(sample.is_verified)
        self.assertEqual(len(sample.text_hash), 64)

    def test_reimport_is_idempotent_and_duplicates_in_file_skipped(self):
        data = self.rows((GOOD, "WATER_SUPPLY"), (GOOD.upper() + "!", "WATER_SUPPLY"))
        first = import_rows(data)
        self.assertEqual((first.imported, first.duplicates), (1, 1))
        second = import_rows(data)
        self.assertEqual((second.imported, second.duplicates), (0, 2))
        self.assertEqual(TrainingSample.objects.count(), 1)

    def test_conflicting_labels_are_reported_not_imported(self):
        report = import_rows(self.rows((GOOD, "WATER_SUPPLY"), (GOOD, "ROADS")))
        self.assertEqual((report.imported, len(report.conflicts)), (1, 1))
        self.assertEqual(TrainingSample.objects.get().department.code, "WATER_SUPPLY")

    def test_invalid_rows_rejected_with_reason(self):
        report = import_rows(self.rows(("test", "ROADS"), ("aaaaaaa aaaaaaa aaaaaaa aaaaaaa", "ROADS"),
                                       (GOOD, "PARKS"), (GOOD, ""), ("", "ROADS")))
        self.assertEqual(report.imported, 0)
        self.assertEqual(len(report.invalid), 3)
        self.assertEqual(sum(report.unknown_departments.values()), 2)

    def test_dry_run_saves_nothing(self):
        report = import_rows(self.rows((GOOD, "WATER_SUPPLY")), dry_run=True)
        self.assertEqual(report.imported, 1)
        self.assertFalse(TrainingSample.objects.exists())

    def test_unverified_rows_are_excluded_from_verified_statistics(self):
        import_rows(self.rows((GOOD, "WATER_SUPPLY")))
        import_rows(self.rows(("Garbage has not been collected for a week now", "SANITATION")), mark_verified=False)
        s = statistics()
        self.assertEqual((s["total_rows"], s["verified_rows"], s["unverified_rows"]), (2, 1, 1))
        self.assertEqual(s["per_class"], {"WATER_SUPPLY": 1})

    def test_csv_missing_columns_and_missing_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as handle:
            csv.writer(handle).writerow(["text", "label"])
        with self.assertRaises(DatasetError):
            read_csv(handle.name)
        with self.assertRaises(DatasetError):
            read_csv("/nonexistent/file.csv")
        with self.assertRaises(CommandError):
            call_command("import_dataset", "/nonexistent/file.csv", verbosity=0)

    def test_statistics_imbalance_ratio(self):
        import_rows(self.rows((GOOD, "WATER_SUPPLY"),
                              ("Garbage has not been collected for a week now", "SANITATION"),
                              ("Garbage is piled up at the corner near the market", "SANITATION")))
        self.assertEqual(statistics()["imbalance_ratio"], 2.0)
