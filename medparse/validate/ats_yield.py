"""ATS diagnostic yield validation helpers."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

from medparse.schema.article import ArticleDocument

FOLLOW_UP_PATTERN = re.compile(r"\b12[-\s]*month diagnostic yield\b", re.IGNORECASE)
FOLLOW_UP_CONSIDERED_PATTERN = re.compile(r"considered diagnostic if follow[-\s]*up", re.IGNORECASE)
INTERMEDIATE_PATTERN = re.compile(r"\b(intermediate|liberal)\s+diagnostic\s+yield\b", re.IGNORECASE)
NONSPECIFIC_TERMS = re.compile(r"\b(atypia|suspicious|nonspecific)\b", re.IGNORECASE)


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
    texts = list(_paragraph_texts(paragraph_store))

    exclusion_reasons: List[str] = list(diagnostic.exclusion_reasons or [])

    has_follow_up_phrase = any(FOLLOW_UP_PATTERN.search(text) for text in texts)
    follow_up_considered = any(FOLLOW_UP_CONSIDERED_PATTERN.search(text) for text in texts)
    has_intermediate_phrase = any(INTERMEDIATE_PATTERN.search(text) for text in texts)
    if has_follow_up_phrase or has_intermediate_phrase:
        exclusion_reasons.append("follow_up_used_in_numerator")
    if follow_up_considered:
        exclusion_reasons.append("follow_up_used_in_numerator")

    strict_claim = bool(getattr(diagnostic, "strict", False) or getattr(diagnostic, "compatible_with_ats", False))
    result["strict_yield_detected"] = strict_claim

    numerator = getattr(diagnostic, "numerator", None)
    denominator = getattr(diagnostic, "denominator", None)
    if strict_claim and (numerator is None or denominator is None):
        exclusion_reasons.append("missing_n_over_N")

    # Flag nonspecific terminology when combined with yield language
    nonspecific_mentions = any(NONSPECIFIC_TERMS.search(text) and "diagnostic" in text for text in texts)
    if nonspecific_mentions:
        exclusion_reasons.append("nonspecific_terms_present")

    exclusion_reasons = list(dict.fromkeys(exclusion_reasons))
    if any(
        "missing_n_over_n" in str(reason).lower()
        or "no_numerator_denominator" in str(reason).lower()
        for reason in exclusion_reasons
    ):
        description = "numerator/denominator not reported at attempted/performed level"
        if not any(description in str(reason) for reason in exclusion_reasons):
            exclusion_reasons.append(description)
    exclusion_reasons = list(dict.fromkeys(exclusion_reasons))

    if strict_claim:
        compatible = not exclusion_reasons and numerator is not None and denominator is not None
    else:
        compatible = not (has_follow_up_phrase or has_intermediate_phrase)
        if exclusion_reasons:
            compatible = False

    diagnostic.exclusion_reasons = exclusion_reasons
    diagnostic.compatible_with_ats = compatible

    result["compatible"] = diagnostic.compatible_with_ats
    result["exclusion_reasons"] = exclusion_reasons
    return result


def _paragraph_texts(paragraph_store: Dict[str, Dict[str, object]]) -> Iterable[str]:
    for entry in paragraph_store.values():
        text = entry.get("text")
        if isinstance(text, str) and text:
            yield text.lower()


__all__ = ["validate_ats_yield"]
