"""Evaluation helpers: standard metrics, confidence-threshold analysis and challenge-set scoring."""
import numpy as np
from django.conf import settings
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

THRESHOLD_GRID = [round(x, 2) for x in np.arange(0.30, 1.0, 0.01)]
REPORT_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)


def classification_metrics(y_true, y_pred, labels) -> dict:
    p, r, f, support = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    pm, rm, fm, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(pm), "recall_macro": float(rm), "f1_macro": float(fm),
        "per_class": {lab: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(support[i])}
                      for i, lab in enumerate(labels)},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "labels": list(labels),
    }


def auto_route_stats(confidence, correct, threshold) -> dict:
    """If complaints with confidence >= threshold were routed automatically: how many, how accurate?"""
    confidence, correct = np.asarray(confidence), np.asarray(correct, dtype=bool)
    auto = confidence >= threshold
    n = int(auto.sum())
    return {"threshold": float(threshold), "auto_routed_share": float(n / max(len(confidence), 1)),
            "auto_routed_accuracy": float(correct[auto].mean()) if n else None, "n": len(confidence)}


def choose_threshold(oof_confidence, oof_correct) -> tuple[float, bool]:
    """
    Smallest threshold (never below ML_MIN_THRESHOLD) whose automatically-routed complaints reach
    ML_TARGET_PRECISION on OUT-OF-FOLD training predictions, so the test sets are not used to pick it.
    Returns (threshold, target_met). If the target cannot be met, a conservative 0.90 is used.
    """
    for t in THRESHOLD_GRID:
        if t < settings.ML_MIN_THRESHOLD:
            continue
        stats = auto_route_stats(oof_confidence, oof_correct, t)
        if stats["auto_routed_accuracy"] is not None and stats["auto_routed_accuracy"] >= settings.ML_TARGET_PRECISION:
            return t, True
    return 0.90, False


def threshold_table(confidence, correct) -> list[dict]:
    return [auto_route_stats(confidence, correct, t) for t in REPORT_THRESHOLDS]
