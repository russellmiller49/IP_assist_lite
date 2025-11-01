"""ATS diagnostic yield validation helpers."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

from medparse.schema.article import ArticleDocument
from medparse.normalize.article_yield_ats import (
    ATS_REASON_NO_N_OVER_N,
    ATS_REASON_FOLLOW_UP,
    ATS_REASON_NONSPECIFIC,
    ATS_REASON_DERIVED,
)

FOLLOW_UP_PATTERN = re.compile(r"\b12[-\s]*month diagnostic yield\b", re.IGNORECASE)
FOLLOW_UP_CONSIDERED_PATTERN = re.compile(r"considered diagnostic if follow[-\s]*up", re.IGNORECASE)
INTERMEDIATE_PATTERN = re.compile(r"\b(intermediate|liberal)\s+diagnostic\s+yield\b", re.IGNORECASE)
NONSPECIFIC_TERMS = re.compile(r"\b(atypia|suspicious|nonspecific)\b", re.IGNORECASE)
N_OVER_N_PATTERN = re.compile(r"\b\d{1,4}\s*/\s*\d{1,4}\b")
STRICT_ANCHOR_PATTERN = re.compile(r"\b(strict|diagnostic yield)\b", re.IGNORECASE)
PROXIMITY_WINDOW = 120
CANONICAL_REASONS = {
    ATS_REASON_NO_N_OVER_N,
    ATS_REASON_FOLLOW_UP,
    ATS_REASON_NONSPECIFIC,
    ATS_REASON_DERIVED,
}


def validate_ats_yield(document: ArticleDocument) -> Dict[str, object]:
    """Validate diagnostic yield fields against ATS strict semantics."""

    result = {
        "strict_yield_detected": False,
        "compatible": True,
        "exclusion_reasons": [],
    }

    diagnostic = getattr(document, "diagnostic_yield", None)
    if diagnostic is None:
        return result

    paragraph_store = getattr(document, "paragraph_store", {}) or {}
    initial_strict_claim = bool(getattr(diagnostic, "strict", False) or getattr(diagnostic, "compatible_with_ats", False))
    texts = list(_paragraph_texts(paragraph_store))

    exclusion_reasons: List[str] = []
    for reason in diagnostic.exclusion_reasons or []:
        normalized = _normalize_reason(reason)
        if normalized and normalized not in exclusion_reasons:
            exclusion_reasons.append(normalized)

    has_follow_up_phrase = any(FOLLOW_UP_PATTERN.search(text) for text in texts)
    follow_up_considered = any(FOLLOW_UP_CONSIDERED_PATTERN.search(text) for text in texts)
    if has_follow_up_phrase or follow_up_considered:
        if ATS_REASON_FOLLOW_UP not in exclusion_reasons:
            exclusion_reasons.append(ATS_REASON_FOLLOW_UP)

    has_intermediate_phrase = any(INTERMEDIATE_PATTERN.search(text) for text in texts)
    if has_intermediate_phrase and ATS_REASON_NONSPECIFIC not in exclusion_reasons:
        exclusion_reasons.append(ATS_REASON_NONSPECIFIC)

    # Flag nonspecific terminology when combined with yield language
    nonspecific_mentions = any(NONSPECIFIC_TERMS.search(text) and "diagnostic" in text for text in texts)
    if nonspecific_mentions and ATS_REASON_NONSPECIFIC not in exclusion_reasons:
        exclusion_reasons.append(ATS_REASON_NONSPECIFIC)

    anchor_seen = any(STRICT_ANCHOR_PATTERN.search(text) for text in texts)
    anchor_with_counts = any(_has_proximal_n_over_n(text) for text in texts)

    numerator = getattr(diagnostic, "numerator", None)
    denominator = getattr(diagnostic, "denominator", None)

    if (numerator is None or denominator is None or (anchor_seen and not anchor_with_counts)) and ATS_REASON_NO_N_OVER_N not in exclusion_reasons:
        exclusion_reasons.append(ATS_REASON_NO_N_OVER_N)

    exclusion_reasons = list(dict.fromkeys(exclusion_reasons))

    blockers = set(exclusion_reasons) & CANONICAL_REASONS
    compatible = (
        numerator is not None
        and denominator is not None
        and not blockers
    )

    exclusion_reasons = [reason for reason in exclusion_reasons if reason in CANONICAL_REASONS]

    diagnostic.strict = bool(compatible)
    diagnostic.exclusion_reasons = exclusion_reasons
    diagnostic.compatible_with_ats = compatible

    result["strict_yield_detected"] = bool(initial_strict_claim or compatible)
    result["compatible"] = diagnostic.compatible_with_ats
    result["exclusion_reasons"] = exclusion_reasons

    return result


def _normalize_reason(reason: Optional[str]) -> Optional[str]:
    if not reason:
        return None
    if reason in CANONICAL_REASONS:
        return reason
    lowered = str(reason).lower()
    if "no_numerator" in lowered or "missing_n_over" in lowered or "no n/" in lowered:
        return ATS_REASON_NO_N_OVER_N
    if "follow_up" in lowered or "follow-up" in lowered or "12-month" in lowered:
        return ATS_REASON_FOLLOW_UP
    if "derived_counts_from_percent" in lowered or ("derived" in lowered and "percent" in lowered):
        return ATS_REASON_DERIVED
    if any(token in lowered for token in ("nonspecific", "composite", "technical success", "per-lesion", "intermediate", "liberal")):
        return ATS_REASON_NONSPECIFIC
    return None


def _has_proximal_n_over_n(text: str, window: int = PROXIMITY_WINDOW) -> bool:
    if not text:
        return False
    for match in STRICT_ANCHOR_PATTERN.finditer(text):
        start = max(0, match.start() - window)
        end = min(len(text), match.end() + window)
        if N_OVER_N_PATTERN.search(text[start:end]):
            return True
    return False


def _paragraph_texts(paragraph_store: Dict[str, Dict[str, object]]) -> Iterable[str]:
    for entry in paragraph_store.values():
        text = entry.get("text")
        if isinstance(text, str) and text:
            yield text.lower()


__all__ = ["validate_ats_yield"]
