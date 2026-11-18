"""
Explainability for the TF-IDF + Multinomial Naive Bayes model.

For a complaint with TF-IDF vector x, Naive Bayes compares classes by
    log P(c) + sum_j x_j * log P(term_j | c).
For the predicted class c and the runner-up class r, a term's contribution to the margin
between them is   x_j * ( log P(term_j | c) - log P(term_j | r) ).
We list the terms with the largest positive contribution.

Honest wording for the UI and report: these are the "influential terms compared with the next
most likely department". They show which words pushed the model toward its answer; they are not
a causal proof, and the prior probabilities also contribute to the final decision.
"""
import numpy as np

from .preprocessing import analyse


def _display_form(feature: str, aligned: list[tuple[str, str]]) -> str:
    """Map a stemmed feature (e.g. 'streetlight' or 'water suppli') back to the words used."""
    stems = [s for s, _ in aligned]
    parts = feature.split(" ")
    for i in range(len(stems) - len(parts) + 1):
        if stems[i:i + len(parts)] == parts:
            return " ".join(w for _, w in aligned[i:i + len(parts)])
    return feature


def influential_terms(pipeline, text: str, predicted_label: str, top_k: int = 5) -> list[dict]:
    tfidf, nb = pipeline.named_steps["tfidf"], pipeline.named_steps["nb"]
    classes = list(nb.classes_)
    if len(classes) < 2 or predicted_label not in classes:
        return []
    x = tfidf.transform([text])
    if x.nnz == 0:
        return []

    log_proba = nb.predict_log_proba(x)[0]
    ci = classes.index(predicted_label)
    runner_up = max((i for i in range(len(classes)) if i != ci), key=lambda i: log_proba[i])

    names = tfidf.get_feature_names_out()
    aligned = analyse(text)
    scored = []
    for j, value in zip(x.indices, x.data):
        margin = float(value * (nb.feature_log_prob_[ci, j] - nb.feature_log_prob_[runner_up, j]))
        if margin > 0:
            scored.append((margin, names[j]))
    scored.sort(reverse=True)

    total = sum(m for m, _ in scored) or 1.0
    terms, used = [], set()
    for margin, feature in scored:
        label = _display_form(feature, aligned)
        if label in used:
            continue
        used.add(label)
        terms.append({"term": label, "score": round(margin, 4), "share": round(margin / total, 3)})
        if len(terms) == top_k:
            break
    return terms


def pipeline_trace(text: str) -> dict:
    """Every stage the model applies to a complaint, for the 'Try the model' page and for explaining the method."""
    from .model_manager import get_active_model
    from .predict import predict
    from .preprocessing import STOP_WORDS, clean_text, tokenize, _stem

    row, pipeline = get_active_model()
    cleaned = clean_text(text)
    tokens = tokenize(cleaned)
    kept = [t for t in tokens if len(t) > 1 and t not in STOP_WORDS]
    removed = [t for t in tokens if t not in kept]
    tfidf = pipeline.named_steps["tfidf"]
    x = tfidf.transform([text])
    names = tfidf.get_feature_names_out()
    weights = sorted(((float(v), names[i]) for i, v in zip(x.indices, x.data)), reverse=True)[:10]
    return {
        "cleaned": cleaned, "tokens": tokens, "removed": removed, "kept": kept, "stems": [_stem(t) for t in kept],
        "features": [{"term": t, "weight": round(w, 3)} for w, t in weights], "feature_count": int(x.nnz),
        "prediction": predict(text), "model": row,
    }
