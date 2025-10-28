"""Statistical classifier fallback for document typing."""

from __future__ import annotations

import warnings
from pathlib import Path

from medparse.classify.rules import classify_with_rules
from medparse.utils.log import get_logger

try:
    import joblib
except ImportError:  # pragma: no cover
    joblib = None  # type: ignore

LOGGER = get_logger(__name__)
MODEL_PATH = Path(__file__).with_suffix(".joblib")


def _validate_sklearn_version(model, model_path: Path) -> None:
    """Check if model was trained with a compatible sklearn version."""
    try:
        from sklearn import __version__ as current_version

        # Try to get the sklearn version the model was trained with
        model_version = getattr(model, "_sklearn_version", None)

        if model_version:
            current_major_minor = tuple(map(int, current_version.split(".")[:2]))
            model_major_minor = tuple(map(int, model_version.split(".")[:2]))

            if current_major_minor != model_major_minor:
                LOGGER.warning(
                    "Model at %s was trained with scikit-learn %s but runtime is %s. "
                    "Consider retraining the model with: python scripts/train_doc_type.py",
                    model_path,
                    model_version,
                    current_version,
                )
    except Exception as e:
        LOGGER.debug("Could not validate sklearn version: %s", e)


def classify_with_model(pdf_path: Path) -> str:
    """Return a doc_type label using a persisted model when available."""
    if joblib and MODEL_PATH.exists():
        try:
            # Suppress sklearn version warnings during load
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
                model = joblib.load(MODEL_PATH)

            # Validate version compatibility
            _validate_sklearn_version(model, MODEL_PATH)

            features = {"path": pdf_path}
            return model.predict([features])[0]
        except Exception as e:
            LOGGER.debug("Model classification failed: %s. Falling back to rules.", e)
            pass
    return classify_with_rules(pdf_path)
