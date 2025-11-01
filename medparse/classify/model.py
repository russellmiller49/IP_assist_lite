"""Statistical classifier fallback for document typing."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Optional

from medparse.classify.rules import classify_with_rules, classify_ifu_subtype as classify_ifu_subtype_rules
from medparse.utils.log import get_logger

try:
    import joblib
except ImportError:  # pragma: no cover
    joblib = None  # type: ignore

LOGGER = get_logger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT_DIR / "models" / "doc_type"
MODEL_PATH = MODEL_DIR / "model.joblib"
MANIFEST_PATH = MODEL_DIR / "MANIFEST.json"


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed to read doc type manifest %s: %s", MANIFEST_PATH, exc)
        return {}


def _validate_sklearn_version(model, manifest: dict, model_path: Path) -> None:
    """Check if model was trained with a compatible sklearn version."""
    try:
        from sklearn import __version__ as current_version

        declared_version = str(manifest.get("sklearn_version") or "")
        model_version = getattr(model, "_sklearn_version", None)

        expected_version = declared_version or model_version
        if not expected_version:
            return

        current_major_minor = tuple(map(int, current_version.split(".")[:2]))
        expected_major_minor = tuple(map(int, str(expected_version).split(".")[:2]))
        if current_major_minor != expected_major_minor:
            LOGGER.warning(
                "Doc-type model at %s targets scikit-learn %s but runtime is %s. "
                "Consider retraining with scripts/train_doc_type.py.",
                model_path,
                expected_version,
                current_version,
            )
    except Exception as exc:
        LOGGER.debug("Could not validate sklearn version: %s", exc)


def classify_with_model(pdf_path: Path) -> str:
    """Return a doc_type label using a persisted model when available."""
    manifest = _load_manifest()
    if not joblib or not MODEL_PATH.exists():
        if manifest and not MODEL_PATH.exists():
            LOGGER.debug("Doc-type manifest present but model missing at %s; using rules.", MODEL_PATH)
        return classify_with_rules(pdf_path)

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
            model = joblib.load(MODEL_PATH)

        _validate_sklearn_version(model, manifest, MODEL_PATH)

        features = [str(pdf_path)]
        return model.predict(features)[0]
    except Exception as exc:
        LOGGER.debug("Model classification failed for %s: %s. Falling back to rules.", pdf_path, exc)
        return classify_with_rules(pdf_path)


def classify_ifu_subtype(pdf_path: Path) -> Optional[str]:
    """Expose IFU subtype heuristics via the model interface."""

    return classify_ifu_subtype_rules(pdf_path)
