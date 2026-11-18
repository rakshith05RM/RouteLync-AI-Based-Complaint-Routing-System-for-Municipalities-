"""Saving, integrity-checking, caching and activating trained models."""
import hashlib
import json
import logging
from pathlib import Path

import joblib
from django.conf import settings

from .exceptions import ModelUnavailableError

logger = logging.getLogger("routelync")
_cache: dict = {}


def models_dir() -> Path:
    path = Path(settings.ML_MODELS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_artefact(pipeline, version: int, metadata: dict) -> tuple[str, str]:
    """Writes model_v{n}.joblib (+ a readable .json with the metrics). Returns (file name, sha256)."""
    name = f"model_v{version}.joblib"
    path = models_dir() / name
    joblib.dump(pipeline, path)
    (models_dir() / f"model_v{version}.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    return name, sha256_of(path)


def clear_cache():
    _cache.clear()


def get_active_model():
    """Returns (MLModel row, fitted pipeline). Raises ModelUnavailableError if it cannot be used."""
    from .models import MLModel

    row = MLModel.objects.filter(is_active=True).first()
    if row is None:
        raise ModelUnavailableError("No active ML model. Train and activate one first.")

    key = (row.pk, row.artefact_sha256)
    if key in _cache:
        return row, _cache[key]

    path = models_dir() / row.artefact_file
    if not path.is_file():
        logger.error("Model artefact missing: %s", path)
        raise ModelUnavailableError("The active model file is missing.")
    # joblib/pickle can execute code when loaded, so verify the file is exactly what we saved.
    if sha256_of(path) != row.artefact_sha256:
        logger.error("Model artefact failed integrity check: %s", path)
        raise ModelUnavailableError("The active model file failed its integrity check.")

    pipeline = joblib.load(path)
    _cache.clear()
    _cache[key] = pipeline
    return row, pipeline
