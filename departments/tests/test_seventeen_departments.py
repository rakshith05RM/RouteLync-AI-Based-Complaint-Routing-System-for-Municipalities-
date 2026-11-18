"""The standard setup covers seventeen municipal departments, and everything that lists departments must agree."""
import csv
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from departments.management.commands.seed_master_data import DEPARTMENTS, STAFF
from departments.models import Department, FieldWorkerProfile, OfficerProfile
from ml_engine.data_generation import ALL_ISSUES, ISSUES, generate
from ml_engine.issues_extra import ISSUES_COLLOQUIAL, ISSUES_EXTRA

ORIGINAL = {"ELECTRICITY", "WATER_SUPPLY", "SANITATION", "ROADS"}


class CatalogTests(TestCase):
    def test_there_are_seventeen_departments_and_every_list_agrees(self):
        codes = {code for _, code, _ in DEPARTMENTS}
        self.assertEqual(len(DEPARTMENTS), 17)
        self.assertEqual(codes, set(STAFF), "every department needs demo staff")
        self.assertEqual(codes, set(ALL_ISSUES), "every department needs training phrases")
        self.assertEqual(codes, set(ISSUES_COLLOQUIAL), "every department needs everyday-speech phrases")
        self.assertEqual(set(ISSUES_EXTRA), codes - ORIGINAL)
        self.assertEqual(set(ISSUES), ORIGINAL)                    # the original four-department data is unchanged
        names = [n for n, _, _ in DEPARTMENTS]
        self.assertEqual(len(set(names)), 17)

    def test_each_department_has_enough_distinct_phrases(self):
        for code, phrases in ALL_ISSUES.items():
            self.assertGreaterEqual(len(phrases), 40, code)
            self.assertEqual(len(phrases), len(set(phrases)), code)

    @override_settings(DEBUG=True)
    def test_seeding_creates_all_with_staff_and_distinct_employee_codes(self):
        call_command("seed_master_data", "--demo-users", "--password", "Demo-Pass#12345", stdout=StringIO())
        self.assertEqual(Department.objects.count(), 17)
        for dept in Department.objects.all():
            self.assertEqual(OfficerProfile.objects.filter(department=dept).count(), 2, dept.code)
            self.assertEqual(OfficerProfile.objects.filter(department=dept, is_department_head=True).count(), 1, dept.code)
            self.assertEqual(FieldWorkerProfile.objects.filter(department=dept).count(), 2, dept.code)
        codes = list(FieldWorkerProfile.objects.values_list("employee_code", flat=True))
        self.assertEqual(len(codes), len(set(codes)))

    def test_seeding_an_existing_installation_adds_the_new_departments_and_changes_nothing_else(self):
        for name, code, description in DEPARTMENTS[:4]:                       # an installation that only had the original four
            Department.objects.create(name=name, code=code, description="edited by the administrator", is_active=(code != "ROADS"))
        before = {d.code: (d.pk, d.description, d.is_active) for d in Department.objects.all()}
        call_command("seed_master_data", stdout=StringIO())
        after = {d.code: (d.pk, d.description, d.is_active) for d in Department.objects.all()}
        self.assertEqual(len(after), 17)
        for code, row in before.items():
            self.assertEqual(after[code], row, code)                           # ids, edited text and the switched-off department are kept

    @override_settings(DEBUG=True)
    def test_every_new_department_has_officers_who_can_sign_in(self):
        call_command("seed_master_data", "--demo-users", "--password", "Demo-Pass#12345", stdout=StringIO())
        from django.core.cache import cache
        cache.clear()
        for key in ("parks", "health", "town", "property", "trade", "fire", "animal", "education", "social", "civil", "traffic", "environment", "advertisements"):
            response = self.client_class().post("/accounts/login/", {"username": f"officer.{key}@routelync.test", "password": "Demo-Pass#12345"})
            self.assertEqual(response.status_code, 302, key)
            self.assertIn("/officer/", response["Location"], key)


class DatasetFileTests(TestCase):
    def rows(self, name):
        with open(Path(settings.DATASETS_DIR) / name, encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_the_original_four_department_file_is_unchanged_and_reproducible(self):
        generated = generate()
        stored = self.rows("complaints_synthetic_v1.csv")
        self.assertEqual(len(stored), 1200)
        self.assertEqual({r["department_code"] for r in stored}, ORIGINAL)
        self.assertEqual([r["text"] for r in generated], [r["text"] for r in stored])

    def test_the_all_department_file_is_reproducible_and_balanced(self):
        stored = self.rows("complaints_synthetic_v2.csv")
        generated = generate(300, 42, ALL_ISSUES, "synthetic_v2")
        self.assertEqual(len(stored), 5100)
        self.assertEqual([r["text"] for r in generated], [r["text"] for r in stored])
        counts = {}
        for r in stored:
            counts[r["department_code"]] = counts.get(r["department_code"], 0) + 1
        self.assertEqual(set(counts), set(ALL_ISSUES))
        self.assertEqual(set(counts.values()), {300})

    def test_no_training_text_belongs_to_two_departments(self):
        owner = {}
        for r in self.rows("complaints_synthetic_v2.csv"):
            text = " ".join(r["text"].lower().split())
            self.assertEqual(owner.setdefault(text, r["department_code"]), r["department_code"], text)

    def test_test_sets_cover_every_department_and_never_appear_in_training(self):
        training = {" ".join(r["text"].lower().split()) for r in self.rows("complaints_synthetic_v2.csv")}
        v2, v3, original = self.rows("challenge_set_v2.csv"), self.rows("challenge_set_v3.csv"), self.rows("challenge_set.csv")
        self.assertEqual(len(original), 64)
        self.assertEqual({r["text"] for r in original} - {r["text"] for r in v2}, set())    # v2 holds the original 64 plus more
        counts = {}
        for r in v2:
            counts[r["department_code"]] = counts.get(r["department_code"], 0) + 1
        self.assertEqual(set(counts), set(ALL_ISSUES))
        self.assertTrue(all(counts[c] >= 10 for c in set(ALL_ISSUES) - ORIGINAL))
        self.assertEqual({r["department_code"] for r in v3}, set(ALL_ISSUES))
        self.assertEqual(len(v3), 51)
        for r in v2 + v3:
            self.assertNotIn(" ".join(r["text"].lower().split()), training, r["text"])
