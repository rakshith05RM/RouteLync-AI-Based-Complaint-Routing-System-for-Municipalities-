from django.core.management.base import BaseCommand, CommandError

from ml_engine.exceptions import MLEngineError
from ml_engine.train import train_and_evaluate


class Command(BaseCommand):
    help = "Train, evaluate and register a new complaint-classification model."

    def add_arguments(self, parser):
        parser.add_argument("--activate", action="store_true", help="Make the new model the active one")
        parser.add_argument("--notes", default="")

    def handle(self, *args, **opts):
        try:
            result = train_and_evaluate(notes=opts["notes"], activate=opts["activate"])
        except MLEngineError as exc:
            raise CommandError(str(exc))
        m = result.ml_model
        out = self.stdout.write
        out(self.style.SUCCESS(f"Model v{m.version} trained{' and ACTIVATED' if m.is_active else ' (not active yet)'}"))
        out(f"Data: {m.dataset_size} samples = {m.train_size} train + {m.test_size} test; classes {m.class_distribution}")
        out(f"Best parameters: {m.best_params}  (cross-validated macro-F1 on training data: {m.cv_f1_macro:.3f})")
        out("")
        out("HELD-OUT TEST SET (stratified 20%)")
        out(f"  accuracy {m.accuracy:.3f} | macro precision {m.precision_macro:.3f} | recall {m.recall_macro:.3f} | F1 {m.f1_macro:.3f}")
        for label, v in m.per_class_metrics.items():
            out(f"  {label:<14} P {v['precision']:.3f}  R {v['recall']:.3f}  F1 {v['f1']:.3f}  n={v['support']}")
        out(f"  confusion matrix (rows = true, columns = predicted; order {m.labels}):")
        for row in m.confusion_matrix:
            out(f"    {row}")
        if m.challenge_report:
            c = m.challenge_report
            out("")
            out("HAND-WRITTEN CHALLENGE SET (never used in training)")
            out(f"  accuracy {c['accuracy']:.3f} | macro F1 {c['f1_macro']:.3f} | by difficulty "
                + ", ".join(f"{k}: {v['accuracy']:.2f} (n={v['n']})" for k, v in c["by_difficulty"].items()))
            for item in c["misclassified"][:8]:
                out(f"  miss: '{item['text'][:60]}' true={item['true']} pred={item['predicted']} conf={item['confidence']}")
        a = m.threshold_analysis
        out("")
        out(f"CONFIDENCE THRESHOLD: {m.conf_threshold} (target precision {a['target_precision']}, met on training OOF: {a['target_met_on_training_oof']})")
        for name in ("test", "challenge"):
            s = a["at_selected_threshold"].get(name)
            if s:
                acc = "n/a" if s["auto_routed_accuracy"] is None else f"{s['auto_routed_accuracy']:.3f}"
                out(f"  {name}: {s['auto_routed_share']:.0%} auto-routed, accuracy of those {acc}")
