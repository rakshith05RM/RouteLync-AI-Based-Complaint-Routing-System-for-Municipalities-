import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from core.geo.providers import inside_area, parse_bbox
from departments.management.commands.seed_karnataka import KARNATAKA_DISTRICTS
from departments.models import Area, Ward


class KarnatakaServiceAreaTests(SimpleTestCase):
    def test_map_starts_over_bengaluru_and_only_the_two_districts_are_supported(self):
        self.assertEqual(parse_bbox(), (12.65, 77.18, 13.50, 77.95))
        self.assertTrue(inside_area(12.9716, 77.5946, "Bengaluru Urban"))
        self.assertTrue(inside_area(13.294, 77.537, "Bengaluru Rural"))
        self.assertTrue(inside_area(12.9716, 77.5946, "Bangalore Urban District"))
        self.assertFalse(inside_area(12.2958, 76.6394, "Mysuru"))

    def test_far_away_places_are_still_refused(self):
        for name in ("Mumbai", "Chennai", "Delhi", "Kochi", "Mysuru"):
            self.assertFalse(inside_area(12.9716, 77.5946, name), name)


class SeedKarnatakaTests(TestCase):
    def test_all_31_districts_with_a_ward_and_it_is_repeatable(self):
        self.assertEqual(len(KARNATAKA_DISTRICTS), 31)
        self.assertEqual(len(set(KARNATAKA_DISTRICTS)), 31)
        call_command("seed_karnataka", verbosity=0)
        call_command("seed_karnataka", verbosity=0)
        self.assertEqual(Area.objects.filter(name__in=KARNATAKA_DISTRICTS).count(), 31)
        self.assertEqual(Ward.objects.filter(area__name__in=KARNATAKA_DISTRICTS).count(), 31)

    def test_existing_wards_are_not_touched(self):
        area = Area.objects.create(name="Mysuru")
        Ward.objects.create(area=area, number=7, name="Real ward")
        call_command("seed_karnataka", verbosity=0)
        self.assertEqual(list(area.wards.values_list("number", flat=True)), [7])


class ImportWardsTests(TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        f.write(text); f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_imports_updates_and_reports_bad_rows(self):
        path = self.write("area,ward_number,ward_name\nMysuru,1,Kuvempunagar\nMysuru,2,\nHubballi,5,Ward 5\nMysuru,abc,Bad\n,3,No area\n")
        call_command("import_wards", path, verbosity=0)
        self.assertEqual(Ward.objects.filter(area__name="Mysuru").count(), 2)
        self.assertEqual(Ward.objects.get(area__name="Mysuru", number=1).name, "Kuvempunagar")
        self.assertEqual(Ward.objects.count(), 3)
        call_command("import_wards", self.write("area,ward_number,ward_name\nMysuru,1,Renamed\n"), verbosity=0)
        self.assertEqual(Ward.objects.get(area__name="Mysuru", number=1).name, "Renamed")
        self.assertEqual(Ward.objects.count(), 3)                  # nothing duplicated or deleted

    def test_dry_run_saves_nothing(self):
        area_count = Area.objects.count()
        call_command("import_wards", self.write("area,ward_number\nMysuru,1\n"), "--dry-run", verbosity=0)
        self.assertEqual(Ward.objects.count(), 0)
        self.assertEqual(Area.objects.count(), area_count)

    def test_wrong_columns_and_missing_file_give_clear_errors(self):
        with self.assertRaises(CommandError):
            call_command("import_wards", self.write("name,number\nx,1\n"), verbosity=0)
        with self.assertRaises(CommandError):
            call_command("import_wards", "/no/such/file.csv", verbosity=0)
