"""Writes docs/ml_results.md from the ACTIVE model's stored evaluation. Every number comes from the database."""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ml_engine.models import MLModel


class Command(BaseCommand):
    help = "Write the machine-learning results (docs/ml_results.md) from the active model."

    def handle(self, *args, **opts):
        m = MLModel.objects.filter(is_active=True).first()
        if m is None:
            raise CommandError("No active model. Run train_complaint_model --activate first.")
        a, c = m.threshold_analysis, m.challenge_report or {}
        L = [f"# Machine-learning results: model v{m.version}", "",
             f"Trained {m.trained_at:%d %b %Y %H:%M}. Pipeline: preprocessing, TF-IDF, Multinomial Naive Bayes. "
             "**The training data is synthetic (generated), not municipal records.** Figures below are the values measured and stored by the training run.", "",
             "## Data and split", "",
             f"- Verified training examples: {m.dataset_size} ({', '.join(f'{k}: {v}' for k, v in sorted(m.class_distribution.items()))})",
             f"- Stratified split (seed {settings.ML_RANDOM_STATE}): {m.train_size} train / {m.test_size} test",
             f"- Best parameters (grid search, cross-validation on the training part only): {m.best_params}",
             f"- Cross-validated macro-F1 on training data: {m.cv_f1_macro:.3f}", "",
             "## Held-out test split", "",
             f"Accuracy {m.accuracy:.3f}; macro precision {m.precision_macro:.3f}; macro recall {m.recall_macro:.3f}; macro F1 {m.f1_macro:.3f}.", "",
             "| Department | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
        L += [f"| {k} | {v['precision']:.3f} | {v['recall']:.3f} | {v['f1']:.3f} | {v['support']} |" for k, v in m.per_class_metrics.items()]
        L += ["", "Confusion matrix (rows = actual, columns = predicted):", "", "| | " + " | ".join(m.labels) + " |", "|---|" + "---|" * len(m.labels)]
        L += [f"| **{lab}** | " + " | ".join(str(x) for x in row) + " |" for lab, row in zip(m.labels, m.confusion_matrix)]
        L += ["", "Generated sentences share building blocks, so a random split of synthetic data is optimistic by construction. "
              "Treat this block as a sanity check, not as the expected real-world accuracy.", ""]
        if c:
            L += ["## Hand-written challenge set (never used in training)", "",
                  f"Accuracy {c['accuracy']:.3f}; macro F1 {c['f1_macro']:.3f}. By difficulty: "
                  + ", ".join(f"{k} {v['accuracy']:.2f} (n={v['n']})" for k, v in c["by_difficulty"].items()) + ".", "",
                  "| Department | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
            L += [f"| {k} | {v['precision']:.3f} | {v['recall']:.3f} | {v['f1']:.3f} | {v['support']} |" for k, v in c["per_class"].items()]
            L += ["", "Misclassified examples:", "", "| Text | True | Predicted | Confidence |", "|---|---|---|---|"]
            L += [f"| {x['text']} | {x['true']} | {x['predicted']} | {x['confidence']} |" for x in c["misclassified"]]
        L += ["", "## Confidence threshold", "",
              f"Selected threshold **{m.conf_threshold}**, chosen from out-of-fold predictions on the training data "
              f"(target precision of auto-routed complaints {a['target_precision']}; target met there: {a['target_met_on_training_oof']}; floor {a['min_threshold']}).", "",
              "| Population | Threshold | Auto-routed share | Accuracy of auto-routed |", "|---|---|---|---|"]
        for name, s in a["at_selected_threshold"].items():
            if s:
                acc = "n/a" if s["auto_routed_accuracy"] is None else f"{s['auto_routed_accuracy']:.3f}"
                L.append(f"| {name} | {s['threshold']} | {s['auto_routed_share']:.0%} | {acc} |")
        L += ["", "A high confidence is not a guarantee: Naive Bayes can be confidently wrong, which is why complaints can be "
              "corrected by an administrator and why only verified corrections are used for retraining.", ""]
        (Path(settings.BASE_DIR) / "docs").mkdir(exist_ok=True)
        (Path(settings.BASE_DIR) / "docs" / "ml_results.md").write_text("\n".join(L))
        self.stdout.write(self.style.SUCCESS("Wrote docs/ml_results.md"))
