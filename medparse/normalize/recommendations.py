"""Guideline recommendation normalization."""

from typing import Iterable, List


def normalize_recommendations(recs: Iterable[dict]) -> List[dict]:
    """Normalize guideline recommendation metadata."""
    normalized: List[dict] = []
    for rec in recs:
        cleaned = dict(rec)
        if grade := cleaned.get("grade"):
            cleaned["grade"] = grade.strip()
        if scale := cleaned.get("strength_scale"):
            cleaned["strength_scale"] = scale.strip()
        normalized.append(cleaned)
    return normalized
