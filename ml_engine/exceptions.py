class MLEngineError(Exception):
    """Base class for ML-related problems."""


class DatasetError(MLEngineError):
    """The dataset file or its contents are unusable."""


class TrainingError(MLEngineError):
    """Training cannot proceed (too little data, one class, ...)."""


class ModelUnavailableError(MLEngineError):
    """No active model, a missing artefact, or an artefact that fails its integrity check."""
