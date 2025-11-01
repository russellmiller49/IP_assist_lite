"""Helpers for parsing and normalizing guideline recommendation grades."""

from __future__ import annotations

import re
from typing import Dict, Optional

CHEST_UNGRADED_PATTERN = re.compile(
    r"^Ungraded\s+Consensus-?Based\s+Statement$", re.IGNORECASE
)

STRENGTH_PATTERN = r"(?P<strength>strong|weak|conditional)\s+recommendation"
QUALITY_PATTERN = r"(?P<quality>very\s+low|low|moderate|high)\s*[-–\s]*quality\s+evidence"
GRADE_RX = re.compile(
    rf"\b{STRENGTH_PATTERN}(?:[,;]?\s+{QUALITY_PATTERN})?", re.IGNORECASE
)

QUALITY_KEYWORDS = {
    "high": "high",
    "moderate": "moderate",
    "low": "low",
    "very low": "very_low",
}


def parse_grade_phrase(text: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
    """Parse a CHEST/GRADE-style strength + quality phrase with tolerant spacing."""

    if not text:
        return None

    match = GRADE_RX.search(text)
    if not match:
        return None

    strength_token = (match.group("strength") or "").strip().lower()
    quality_token = match.group("quality")

    if not strength_token:
        return None

    strength_normalized = "strong" if strength_token == "strong" else "weak"
    if strength_token == "conditional":
        strength_normalized = "weak"

    quality_normalized: Optional[str] = None
    if quality_token:
        normalized = re.sub(r"[-–]+", " ", quality_token.lower()).strip()
        quality_normalized = QUALITY_KEYWORDS.get(normalized)

    raw_phrase = match.group(0).strip(" ,.;")

    payload: Dict[str, Optional[str]] = {
        "scale": "GRADE",
        "strength": strength_normalized,
        "quality": quality_normalized,
        "raw": raw_phrase,
    }
    return payload


def _normalize_quality(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.lower()
    for phrase, normalized in QUALITY_KEYWORDS.items():
        if phrase in lowered:
            return normalized
    quality_match = re.search(r"grade\s+([a-d])", lowered)
    if quality_match:
        letter = quality_match.group(1)
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

    grade_info = parse_grade_phrase(grade_raw) or parse_grade_phrase(text)
    if grade_info:
        normalized: Dict[str, Optional[str]] = {
            "scale": grade_info.get("scale") or "GRADE",
            "strength": grade_info.get("strength"),
            "quality": grade_info.get("quality"),
            "raw": grade_info.get("raw"),
        }
        if grade_info.get("quality"):
            normalized["evidence_quality"] = grade_info["quality"]
        # Remove None before returning
        return {k: v for k, v in normalized.items() if v is not None}

    normalized: Dict[str, Optional[str]] = {}

    if strength:
        normalized["strength"] = strength.lower()

    quality = _normalize_quality(evidence_level)
    if quality:
        normalized["quality"] = quality
        normalized["evidence_quality"] = quality

    scale_value = scale_hint.upper() if scale_hint else None

    if grade_raw:
        grade_clean = grade_raw.strip()
        if CHEST_UNGRADED_PATTERN.match(grade_clean):
            normalized["strength"] = "ungraded"
            normalized["scale"] = "Consensus"
            return normalized

        grade_upper = grade_clean.upper()
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

    return {key: value for key, value in normalized.items() if value is not None} or None


__all__ = ["normalize_grade", "parse_grade_phrase"]
