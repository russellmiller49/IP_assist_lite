"""Statistical classifier fallback for document typing."""

from __future__ import annotations

from pathlib import Path

from medparse.classify.rules import classify_with_rules

try:
    import joblib
except ImportError:  # pragma: no cover
    joblib = None  # type: ignore


MODEL_PATH = Path(__file__).with_suffix(".joblib")


def classify_with_model(pdf_path: Path) -> str:
    """Return a doc_type label using a persisted model when available."""
    if joblib and MODEL_PATH.exists():
        try:
            model = joblib.load(MODEL_PATH)
            features = {"path": pdf_path}
            return model.predict([features])[0]
        except Exception:
            pass
    return classify_with_rules(pdf_path)
