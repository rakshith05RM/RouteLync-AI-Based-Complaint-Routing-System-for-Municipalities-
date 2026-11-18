from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from ml_engine.data_generation import ALL_ISSUES, generate, write_csv


class Command(BaseCommand):
    help = "Generate the SYNTHETIC training CSV (deterministic). Not municipal data."

    def add_arguments(self, parser):
        parser.add_argument("--per-class", type=int, default=300)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--all-departments", action="store_true", help="Generate for every department (writes complaints_synthetic_v2.csv)")
        parser.add_argument("--output", default=None)

    def handle(self, *args, **opts):
        everything = opts["all_departments"]
        output = opts["output"] or str(Path(settings.DATASETS_DIR) / ("complaints_synthetic_v2.csv" if everything else "complaints_synthetic_v1.csv"))
        rows = generate(opts["per_class"], opts["seed"], ALL_ISSUES if everything else None, "synthetic_v2" if everything else "synthetic_v1")
        write_csv(Path(output), rows)
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows)} synthetic rows to {output}"))
