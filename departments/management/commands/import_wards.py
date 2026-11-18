"""
Loads areas and wards from a CSV file.

    python manage.py import_wards wards.csv            # check, then save
    python manage.py import_wards wards.csv --dry-run  # only report what would happen

Columns (header row required): area, ward_number, ward_name   (ward_name is optional)
Example:
    area,ward_number,ward_name
    Mysuru,1,Ward 1 Kuvempunagar
    Mysuru,2,Ward 2
Existing areas/wards are reused; a ward's name is updated. Nothing is ever deleted. Rows with problems are skipped and listed.
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from departments.models import Area, Ward

MAX_BYTES = 5_000_000


class Command(BaseCommand):
    help = "Import areas and wards from a CSV file (columns: area, ward_number, ward_name)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--dry-run", action="store_true", help="Report only; save nothing.")

    def handle(self, *args, **opts):
        try:
            with open(opts["csv_path"], newline="", encoding="utf-8-sig") as fh:
                raw = fh.read(MAX_BYTES + 1)
        except OSError as exc:
            raise CommandError(f"Cannot read the file: {exc.strerror}")
        if len(raw) > MAX_BYTES:
            raise CommandError("The file is larger than 5 MB.")
        reader = csv.DictReader(raw.splitlines())
        fields = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
        if not {"area", "ward_number"} <= fields:
            raise CommandError("The first row must contain the columns: area, ward_number (and optionally ward_name).")

        problems, rows = [], []
        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            area, number, name = row.get("area", ""), row.get("ward_number", ""), row.get("ward_name", "")
            if not area or len(area) > 100 or len(name) > 100:
                problems.append(f"line {line_no}: area is missing or a name is longer than 100 characters")
            elif not number.isdigit() or not 1 <= int(number) <= 32767:
                problems.append(f"line {line_no}: ward_number must be a whole number from 1 to 32767")
            else:
                rows.append((area, int(number), name))

        new_areas = new_wards = updated = 0
        with transaction.atomic():
            for area_name, number, name in rows:
                area, area_created = Area.objects.get_or_create(name=area_name)
                new_areas += area_created
                ward, ward_created = Ward.objects.get_or_create(area=area, number=number, defaults={"name": name})
                if ward_created:
                    new_wards += 1
                elif name and ward.name != name:
                    ward.name = name
                    ward.save(update_fields=["name"])
                    updated += 1
            if opts["dry_run"]:
                transaction.set_rollback(True)

        prefix = "DRY RUN (nothing saved): " if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}{len(rows)} row(s) read: {new_areas} area(s) and {new_wards} ward(s) added, {updated} ward name(s) updated."))
        for p in problems[:20]:
            self.stdout.write(self.style.WARNING(f"Skipped {p}"))
        if len(problems) > 20:
            self.stdout.write(self.style.WARNING(f"... and {len(problems) - 20} more skipped rows."))
