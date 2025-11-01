"""Canonical mappings for guideline grading schemes."""

from __future__ import annotations

import re
from typing import Dict, Optional

# Allowed vocab tokens for certainty normalization
CERTAINTY_CANONICAL = {
    "very low": "very_low",
    "very-low": "very_low",
    "moderate": "moderate",
    "low": "low",
    "high": "high",
    "very_low": "very_low",
}

GRADE_LETTER_TO_CERTAINTY = {
    "A": "high",
    "B": "moderate",
    "C": "low",
    "D": "very_low",
}

# Strength tokens collapsed to canonical buckets
STRENGTH_CANONICAL = {
    "strong": "strong",
    "conditional": "conditional",
    "weak": "conditional",
}


def _clamp_confidence(confidence: float, *, minimum: float = 0.6, maximum: float = 0.95) -> float:
    return max(minimum, min(maximum, round(confidence, 3)))


def canonicalize_strength(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    return STRENGTH_CANONICAL.get(lowered)


def canonicalize_certainty(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in CERTAINTY_CANONICAL:
        return CERTAINTY_CANONICAL[lowered]
    lowered = lowered.replace("certainty in evidence", "certainty")
    lowered = lowered.replace("quality of evidence", "certainty")
    lowered = lowered.replace("quality", "").strip()
    for token, canonical in CERTAINTY_CANONICAL.items():
        if token in lowered:
            return canonical
    return None


def _detect_scale_from_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    upper = text.upper()
    if any(token in upper for token in ("CHEST", "AMERICAN COLLEGE OF CHEST PHYSICIANS", "ACCP")):
        return "CHEST"
    if "UNGRADED CONSENSUS-BASED" in upper or re.search(r"\bUCS\b", upper):
        return "CHEST"
    if "ESGE" in upper or "EUROPEAN SOCIETY OF GASTROINTESTINAL ENDOSCOPY" in upper:
        return "ESGE_ERS_ESTS"
    if "ERS/ESTS" in upper or ("ERS" in upper and "ESTS" in upper):
        return "ESGE_ERS_ESTS"
    if "ATS/ERS" in upper:
        return "ATS_ERS"
    if re.search(r"\bATS\b", upper) or "AMERICAN THORACIC SOCIETY" in upper or "EUROPEAN RESPIRATORY SOCIETY" in upper:
        return "ATS_ERS"
    if "SIGN" in upper:
        return "SIGN"
    if "GRADE" in upper:
        return "GRADE"
    if "CONSENSUS" in upper or "GOOD PRACTICE" in upper or "BEST PRACTICE" in upper:
        return "CONSENSUS"
    return None


def canonicalize_scale(
    value: Optional[str],
    *,
    raw: Optional[str] = None,
    hint: Optional[str] = None,
) -> Optional[str]:
    for candidate in (hint, raw, value):
        detected = _detect_scale_from_text(candidate)
        if detected:
            return detected
    if value:
        return value.strip().upper()
    return None


def build_envelope(
    *,
    scale: str,
    source: str,
    confidence: float,
    strength: Optional[str] = None,
    letter: Optional[str] = None,
    certainty: Optional[str] = None,
    ungraded: bool = False,
    raw: Optional[str] = None,
    code: Optional[str] = None,
    scale_hint: Optional[str] = None,
) -> Dict[str, object]:
    """Construct the normalized grade envelope used across the pipeline."""

    canonical_scale = canonicalize_scale(scale, raw=raw, hint=scale_hint)
    payload: Dict[str, object] = {
        "scale": canonical_scale,
        "source": source,
        "confidence": _clamp_confidence(confidence),
        "ungraded": bool(ungraded),
    }
    if strength:
        payload["strength"] = strength
    if letter:
        payload["letter"] = letter.upper()
    if certainty:
        payload["certainty"] = certainty
    if raw:
        payload["raw"] = raw
    if code:
        payload["code"] = code.upper()

    value_token = None
    if code:
        value_token = code.upper()
    elif letter:
        value_token = letter.upper()
    elif strength:
        value_token = strength
    elif certainty:
        value_token = certainty
    if value_token:
        payload["value"] = value_token

    payload.setdefault("graded", not bool(ungraded))
    payload.setdefault("typed", True)
    return payload


def map_sign_letter(
    letter: Optional[str],
    *,
    source: str,
    confidence: float,
    raw: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    if not letter:
        return None
    normalized_letter = letter.strip().upper()
    if normalized_letter not in {"A", "B", "C", "D"}:
        return None
    return build_envelope(
        scale="SIGN",
        source=source,
        confidence=confidence,
        letter=normalized_letter,
        ungraded=False,
        raw=raw,
    )


def map_grade_strength(
    strength: Optional[str],
    certainty: Optional[str],
    *,
    source: str,
    confidence: float,
    raw: Optional[str] = None,
    scale_hint: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    canonical_strength = canonicalize_strength(strength)
    canonical_certainty = canonicalize_certainty(certainty)
    if not canonical_strength and not canonical_certainty:
        return None
    return build_envelope(
        scale="GRADE",
        source=source,
        confidence=confidence,
        strength=canonical_strength,
        certainty=canonical_certainty,
        raw=raw,
        scale_hint=scale_hint,
    )


def map_grade_code(
    number: Optional[str],
    letter: Optional[str],
    *,
    source: str,
    confidence: float,
    raw: Optional[str] = None,
    scale_hint: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    if not number or not letter:
        return None
    normalized_number = str(number).strip()
    normalized_letter = str(letter).strip().upper()
    if normalized_number not in {"1", "2"}:
        return None
    if normalized_letter not in GRADE_LETTER_TO_CERTAINTY:
        return None
    strength = "strong" if normalized_number == "1" else "conditional"
    certainty = GRADE_LETTER_TO_CERTAINTY[normalized_letter]
    code = f"{normalized_number}{normalized_letter}"
    return build_envelope(
        scale="GRADE",
        source=source,
        confidence=confidence,
        strength=strength,
        certainty=certainty,
        letter=normalized_letter,
        raw=raw or code,
        code=code,
        scale_hint=scale_hint,
    )


def map_consensus(
    *,
    source: str,
    confidence: float,
    raw: Optional[str] = None,
    scale_hint: Optional[str] = None,
) -> Dict[str, object]:
    return build_envelope(
        scale="CONSENSUS",
        source=source,
        confidence=confidence,
        strength=None,
        certainty=None,
        ungraded=True,
        raw=raw,
        scale_hint=scale_hint,
    )


__all__ = [
    "build_envelope",
    "canonicalize_certainty",
    "canonicalize_scale",
    "canonicalize_strength",
    "map_consensus",
    "map_grade_strength",
    "map_grade_code",
    "map_sign_letter",
]
