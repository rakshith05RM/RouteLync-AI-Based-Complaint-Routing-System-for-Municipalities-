from django.core.management.base import BaseCommand, CommandError

from ml_engine.dataset import import_rows, read_csv
from ml_engine.exceptions import DatasetError
from ml_engine.models import TrainingSample


class Command(BaseCommand):
    help = "Validate and import a labelled CSV (columns: text, department_code [, source, is_verified, dataset_version])."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--source", choices=[c for c, _ in TrainingSample.Source.choices], default="IMPORTED")
        parser.add_argument("--dataset-version", default="", help="Dataset version label")
        parser.add_argument("--unverified", action="store_true", help="Import rows as NOT verified (excluded from training)")
        parser.add_argument("--dry-run", action="store_true", help="Validate only; save nothing")

    def handle(self, *args, **opts):
        try:
            rows = read_csv(opts["csv_path"])
        except DatasetError as exc:
            raise CommandError(str(exc))
        report = import_rows(rows, source=opts["source"], version=opts["dataset_version"],
                             mark_verified=not opts["unverified"], dry_run=opts["dry_run"])
        self.stdout.write(report.summary())
        for number, reason in report.invalid[:10]:
            self.stdout.write(self.style.WARNING(f"  row {number}: {reason}"))
        for number, text, old, new in report.conflicts[:10]:
            self.stdout.write(self.style.WARNING(f"  row {number}: label conflict ({old} vs {new}): {text}"))
        for code, n in report.unknown_departments.items():
            self.stdout.write(self.style.WARNING(f"  unknown department '{code}': {n} row(s)"))
