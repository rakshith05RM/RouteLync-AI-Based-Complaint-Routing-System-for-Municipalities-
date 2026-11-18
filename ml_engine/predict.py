"""Prediction service used by the routing code (Phase 6). Views never touch scikit-learn directly."""
from dataclasses import dataclass, field

from .exceptions import ModelUnavailableError  # noqa: F401  (re-exported for callers)
from .explain import influential_terms
from .model_manager import get_active_model
from .preprocessing import preprocess_text


@dataclass(frozen=True)
class Prediction:
    department_code: str | None
    confidence: float
    probabilities: dict
    top_terms: list = field(default_factory=list)
    cleaned_text: str = ""
    model_id: int | None = None
    model_version: int | None = None
    threshold: float = 0.0
    needs_verification: bool = True
    reason: str = ""      # "", "low_confidence", "no_usable_text", "no_known_terms"


def predict(text: str, *, threshold: float | None = None) -> Prediction:
    """
    Raises ModelUnavailableError if no usable model exists; the caller must then send the complaint
    to manual verification instead of guessing.
    """
    row, pipeline = get_active_model()
    limit = row.conf_threshold if threshold is None else threshold
    base = dict(model_id=row.pk, model_version=row.version, threshold=limit)

    cleaned = preprocess_text(text)
    if not cleaned:
        return Prediction(None, 0.0, {}, cleaned_text=cleaned, reason="no_usable_text", **base)

    if pipeline.named_steps["tfidf"].transform([text]).nnz == 0:
        # None of the words were seen in training: Naive Bayes would just return its priors.
        return Prediction(None, 0.0, {}, cleaned_text=cleaned, reason="no_known_terms", **base)

    proba = pipeline.predict_proba([text])[0]
    classes = [str(c) for c in pipeline.named_steps["nb"].classes_]
    best = int(proba.argmax())
    confidence = float(proba[best])
    low = confidence < limit
    return Prediction(
        department_code=classes[best], confidence=confidence,
        probabilities={c: float(p) for c, p in sorted(zip(classes, proba), key=lambda cp: -cp[1])},
        top_terms=influential_terms(pipeline, text, classes[best]), cleaned_text=cleaned,
        needs_verification=low, reason="low_confidence" if low else "", **base)
