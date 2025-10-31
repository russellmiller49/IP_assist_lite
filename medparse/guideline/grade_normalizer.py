"""Helpers for normalizing guideline recommendation grades."""

from __future__ import annotations

import re
from typing import Dict, Optional


QUALITY_KEYWORDS = {
    "high": "high",
    "moderate": "moderate",
    "low": "low",
    "very low": "very_low",
}


def _normalize_quality(value: str | None) -> Optional[str]:
    if not value:
        return None
    lowered = value.lower()
    for phrase, normalized in QUALITY_KEYWORDS.items():
        if phrase in lowered:
            return normalized
    if re.search(r"grade\s+([a-d])", lowered):
        letter = re.search(r"grade\s+([a-d])", lowered).group(1)
        if letter in {"a", "b"}:
            return "high"
        if letter == "c":
            return "moderate"
        return "low"
    return None


def normalize_grade(
    grade_raw: Optional[str],
    strength: Optional[str],
    evidence_level: Optional[str],
    scale_hint: Optional[str] = None,
    *,
    text: Optional[str] = None,
) -> Optional[Dict[str, Optional[str]]]:
    """Normalize guideline grading metadata into strength/quality/scale."""

    normalized: Dict[str, Optional[str]] = {}

    if strength:
        normalized["strength"] = strength.lower()

    quality = _normalize_quality(evidence_level) or _normalize_quality(text)
    if quality:
        normalized["quality"] = quality

    scale_value = scale_hint.upper() if scale_hint else None

    if grade_raw:
        grade_upper = grade_raw.strip().upper()
        if grade_upper in {"A", "B", "C", "D"}:
            scale_value = "SIGN"
            normalized.setdefault(
                "strength",
                "strong" if grade_upper in {"A", "B"} else "weak",
            )
        elif grade_upper.startswith("1"):
            scale_value = scale_value or "GRADE"

    if scale_value:
        normalized["scale"] = scale_value
    elif normalized:
        normalized.setdefault("scale", "GRADE" if normalized.get("quality") else None)

    # Remove None values for cleanliness
    normalized = {key: value for key, value in normalized.items() if value is not None}
    return normalized or None


__all__ = ["normalize_grade"]

