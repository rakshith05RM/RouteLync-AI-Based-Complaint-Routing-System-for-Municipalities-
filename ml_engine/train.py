"""
Training service. Never called from a request: run `manage.py train_complaint_model`.

    verified TrainingSamples -> validate -> stratified 80/20 split
      -> grid search with cross-validation on the TRAINING part only
      -> final evaluation on the untouched TEST part (+ separate hand-written challenge set)
      -> choose confidence threshold from out-of-fold training predictions
      -> save artefact + register MLModel (activation is a separate step)
"""
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from django.conf import settings
from django.db.models import Max
from sklearn.base import clone
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict, train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from .dataset import read_csv
from .evaluate import auto_route_stats, choose_threshold, classification_metrics, threshold_table
from .exceptions import DatasetError, TrainingError
from .model_manager import save_artefact
from .models import MLModel, TrainingSample
from .preprocessing import preprocess_text, whitespace_tokens

logger = logging.getLogger("routelync")

PARAM_GRID = {
    "tfidf__ngram_range": [(1, 1), (1, 2)],
    "tfidf__min_df": [1, 2],
    "nb__alpha": [0.01, 0.03, 0.1, 0.3, 1.0],   # alpha = Laplace/Lidstone smoothing strength
}


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(preprocessor=preprocess_text, tokenizer=whitespace_tokens, token_pattern=None,
                                  lowercase=False, sublinear_tf=True)),
        ("nb", MultinomialNB()),
    ])


@dataclass
class TrainingResult:
    ml_model: MLModel
    train_texts: list = field(default_factory=list)
    test_texts: list = field(default_factory=list)
    challenge_texts: list = field(default_factory=list)


def load_training_data():
    samples = TrainingSample.objects.filter(is_verified=True).select_related("department")
    texts = [s.text for s in samples]
    labels = [s.department.code for s in samples]
    if not texts:
        raise TrainingError("There are no verified training samples. Import a dataset first.")
    counts = Counter(labels)
    if len(counts) < 2:
        raise TrainingError("Training needs at least two departments with samples.")
    small = {c: n for c, n in counts.items() if n < settings.ML_MIN_SAMPLES_PER_CLASS}
    if small:
        raise TrainingError(f"Too few samples (minimum {settings.ML_MIN_SAMPLES_PER_CLASS} per department): {small}")
    return texts, labels, counts


def _evaluate_challenge(pipeline, labels, path: Path):
    """Score the hand-written challenge set. Returns (report dict, texts) or (None, [])."""
    if not path.is_file():
        return None, []
    try:
        rows = read_csv(path)
    except DatasetError:
        return None, []
    rows = [r for r in rows if (r.get("department_code") or "").strip().upper() in labels]
    if not rows:
        return None, []
    texts = [r["text"].strip() for r in rows]
    truth = [r["department_code"].strip().upper() for r in rows]
    proba = pipeline.predict_proba(texts)
    classes = [str(c) for c in pipeline.named_steps["nb"].classes_]
    pred = [classes[i] for i in proba.argmax(axis=1)]
    conf = proba.max(axis=1)
    correct = np.array([p == t for p, t in zip(pred, truth)])

    by_difficulty = {}
    for level in sorted({(r.get("difficulty") or "normal") for r in rows}):
        idx = [i for i, r in enumerate(rows) if (r.get("difficulty") or "normal") == level]
        by_difficulty[level] = {"n": len(idx), "accuracy": float(correct[idx].mean())}

    metrics = classification_metrics(truth, pred, labels)
    metrics["by_difficulty"] = by_difficulty
    metrics["threshold_table"] = threshold_table(conf, correct)
    metrics["misclassified"] = [
        {"text": texts[i], "true": truth[i], "predicted": pred[i], "confidence": round(float(conf[i]), 3)}
        for i in range(len(texts)) if not correct[i]]
    return metrics, texts, conf, correct


def train_and_evaluate(*, user=None, notes="", activate=False, challenge_path=None) -> TrainingResult:
    texts, labels, counts = load_training_data()
    seed = settings.ML_RANDOM_STATE

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=settings.ML_TEST_SIZE, stratify=labels, random_state=seed)

    folds = max(2, min(5, min(Counter(y_train).values())))
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    search = GridSearchCV(build_pipeline(), PARAM_GRID, scoring="f1_macro", cv=cv, n_jobs=1, refit=True)
    search.fit(X_train, y_train)                 # tuning sees the training part only
    pipeline = search.best_estimator_
    classes = [str(c) for c in pipeline.named_steps["nb"].classes_]

    # ---- the one-and-only look at the held-out test set
    proba_test = pipeline.predict_proba(X_test)
    pred_test = [classes[i] for i in proba_test.argmax(axis=1)]
    conf_test = proba_test.max(axis=1)
    correct_test = np.array([p == t for p, t in zip(pred_test, y_test)])
    test_metrics = classification_metrics(y_test, pred_test, classes)

    # ---- threshold chosen from out-of-fold predictions on TRAINING data only
    oof = cross_val_predict(clone(pipeline), X_train, y_train, cv=cv, method="predict_proba")
    oof_pred = np.array([classes[i] for i in oof.argmax(axis=1)])
    oof_conf = oof.max(axis=1)
    oof_correct = oof_pred == np.array(y_train)
    threshold, target_met = choose_threshold(oof_conf, oof_correct)

    # ---- hand-written challenge set (never part of training)
    if challenge_path:
        path = Path(challenge_path)
    else:                                  # the v2 file holds the original 64 rows plus rows for the added departments;
        v2 = Path(settings.DATASETS_DIR) / "challenge_set_v2.csv"       # rows for departments the model does not know are skipped
        path = v2 if v2.is_file() else Path(settings.DATASETS_DIR) / "challenge_set.csv"
    challenge = _evaluate_challenge(pipeline, classes, path)
    challenge_metrics, challenge_texts = (challenge[0], challenge[1]) if challenge[0] else (None, [])

    analysis = {
        "selected_threshold": threshold, "target_precision": settings.ML_TARGET_PRECISION,
        "target_met_on_training_oof": target_met, "min_threshold": settings.ML_MIN_THRESHOLD,
        "out_of_fold_training": threshold_table(oof_conf, oof_correct),
        "test": threshold_table(conf_test, correct_test),
        "challenge": challenge_metrics["threshold_table"] if challenge_metrics else None,
        "at_selected_threshold": {
            "test": auto_route_stats(conf_test, correct_test, threshold),
            "challenge": auto_route_stats(challenge[2], challenge[3], threshold) if challenge_metrics else None,
        },
    }

    version = (MLModel.objects.aggregate(m=Max("version"))["m"] or 0) + 1
    metadata = {
        "version": version, "labels": classes, "best_params": {k: str(v) for k, v in search.best_params_.items()},
        "test": test_metrics, "challenge": challenge_metrics, "threshold": analysis,
        "dataset_size": len(texts), "train_size": len(X_train), "test_size": len(X_test),
        "random_state": seed, "sklearn_pipeline": "TfidfVectorizer -> MultinomialNB",
    }
    file_name, digest = save_artefact(pipeline, version, metadata)

    ml_model = MLModel.objects.create(
        version=version, artefact_file=file_name, artefact_sha256=digest, labels=classes,
        dataset_size=len(texts), train_size=len(X_train), test_size=len(X_test), class_distribution=dict(counts),
        accuracy=test_metrics["accuracy"], precision_macro=test_metrics["precision_macro"],
        recall_macro=test_metrics["recall_macro"], f1_macro=test_metrics["f1_macro"],
        per_class_metrics=test_metrics["per_class"], confusion_matrix=test_metrics["confusion_matrix"],
        challenge_accuracy=challenge_metrics["accuracy"] if challenge_metrics else None,
        challenge_report=challenge_metrics,
        best_params=metadata["best_params"], cv_f1_macro=float(search.best_score_),
        conf_threshold=threshold, threshold_analysis=analysis, trained_by=user, notes=notes[:255])
    from audit.services import log_action
    log_action(user, "MODEL_TRAINED", target=ml_model, summary=f"Model v{version} trained (test accuracy {test_metrics['accuracy']:.3f})",
               details={"dataset_size": len(texts), "accuracy": test_metrics["accuracy"], "challenge_accuracy": ml_model.challenge_accuracy})
    if activate:
        ml_model.activate(user)
    logger.info("Trained model v%s (test accuracy %.3f)", version, test_metrics["accuracy"])
    return TrainingResult(ml_model=ml_model, train_texts=list(X_train), test_texts=list(X_test),
                          challenge_texts=challenge_texts)
