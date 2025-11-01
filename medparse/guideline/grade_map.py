"""Canonical mappings for guideline grading schemes."""

from __future__ import annotations

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
) -> Dict[str, object]:
    """Construct the normalized grade envelope used across the pipeline."""

    payload: Dict[str, object] = {
        "scale": scale.upper(),
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
    )


def map_consensus(
    *,
    source: str,
    confidence: float,
    raw: Optional[str] = None,
) -> Dict[str, object]:
    return build_envelope(
        scale="CONSENSUS",
        source=source,
        confidence=confidence,
        strength=None,
        certainty=None,
        ungraded=True,
        raw=raw,
    )


__all__ = [
    "build_envelope",
    "canonicalize_certainty",
    "canonicalize_strength",
    "map_consensus",
    "map_grade_strength",
    "map_sign_letter",
]
