"""Score the ACTIVE model on any labelled CSV (text, department_code): accuracy, per-department results and the confusions.

    python manage.py evaluate_model datasets/challenge_set_v3.csv
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from ml_engine.dataset import DatasetError, read_csv
from ml_engine.exceptions import ModelUnavailableError
from ml_engine.model_manager import get_active_model


class Command(BaseCommand):
    help = "Evaluate the active model on a labelled CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv")

    def handle(self, *args, **opts):
        try:
            rows = read_csv(opts["csv"])
        except DatasetError as exc:
            raise CommandError(str(exc))
        try:
            _, pipeline = get_active_model()
        except ModelUnavailableError as exc:
            raise CommandError(str(exc))
        classes = [str(c) for c in pipeline.classes_]
        known = [r for r in rows if r["department_code"].strip().upper() in classes]
        skipped = len(rows) - len(known)
        texts = [r["text"].strip() for r in known]
        truth = [r["department_code"].strip().upper() for r in known]
        proba = pipeline.predict_proba(texts)
        pred = [classes[i] for i in proba.argmax(axis=1)]
        conf = proba.max(axis=1)
        right = sum(p == t for p, t in zip(pred, truth))
        self.stdout.write(f"{opts['csv']}: {right}/{len(known)} correct = {right / max(len(known), 1):.3f}"
                          + (f" ({skipped} rows skipped: department unknown to the model)" if skipped else ""))
        per = Counter(); tot = Counter()
        for p, t in zip(pred, truth):
            tot[t] += 1; per[t] += p == t
        for code in sorted(tot, key=lambda c: per[c] / tot[c]):
            self.stdout.write(f"  {code:20} {per[code]}/{tot[code]}")
        for text, t, p, c in zip(texts, truth, pred, conf):
            if p != t:
                self.stdout.write(f"  MISS true={t} predicted={p} confidence={c:.2f} | {text[:80]}")
