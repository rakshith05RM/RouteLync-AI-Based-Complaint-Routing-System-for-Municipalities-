from django.core.management.base import BaseCommand

from ml_engine.dataset import statistics


class Command(BaseCommand):
    help = "Show training-dataset size, class balance and text lengths."

    def handle(self, *args, **opts):
        s = statistics()
        self.stdout.write(f"Rows: {s['total_rows']} (verified {s['verified_rows']}, unverified {s['unverified_rows']})")
        for code, n in sorted(s["per_class"].items()):
            self.stdout.write(f"  {code:<14} {n}")
        self.stdout.write(f"Imbalance ratio (largest/smallest class): {s['imbalance_ratio']}")
        self.stdout.write(f"Words per text: mean {s['mean_words']}, min {s['min_words']}, max {s['max_words']}")
        self.stdout.write(f"By source: {s['by_source']}")
