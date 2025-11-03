"""ATS diagnostic yield validation helpers."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

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
    ordered_paragraphs = _ordered_paragraphs(paragraph_store)
    texts = [text for _order, _page, text in ordered_paragraphs]

    initial_strict_claim = bool(getattr(diagnostic, "strict", False) or getattr(diagnostic, "compatible_with_ats", False))

    exclusion_reasons: List[str] = []
    for reason in diagnostic.exclusion_reasons or []:
        normalized = _normalize_reason(reason)
        if normalized and normalized not in exclusion_reasons:
            exclusion_reasons.append(normalized)

    if any(FOLLOW_UP_PATTERN.search(text) for text in texts) or any(FOLLOW_UP_CONSIDERED_PATTERN.search(text) for text in texts):
        if ATS_REASON_FOLLOW_UP not in exclusion_reasons:
            exclusion_reasons.append(ATS_REASON_FOLLOW_UP)

    if any(INTERMEDIATE_PATTERN.search(text) for text in texts) and ATS_REASON_NONSPECIFIC not in exclusion_reasons:
        exclusion_reasons.append(ATS_REASON_NONSPECIFIC)

    if any(NONSPECIFIC_TERMS.search(text) and "diagnostic" in text for text in texts) and ATS_REASON_NONSPECIFIC not in exclusion_reasons:
        exclusion_reasons.append(ATS_REASON_NONSPECIFIC)

    strict_indices = _strict_anchor_indices(ordered_paragraphs)

    numerator = getattr(diagnostic, "numerator", None)
    denominator = getattr(diagnostic, "denominator", None)

    if (numerator is None or denominator is None) and ATS_REASON_NO_N_OVER_N not in exclusion_reasons:
        exclusion_reasons.append(ATS_REASON_NO_N_OVER_N)

    counts_adjacent = True
    if strict_indices:
        counts_adjacent = _anchors_have_adjacent_counts(ordered_paragraphs, strict_indices)
        if not counts_adjacent and ATS_REASON_NO_N_OVER_N not in exclusion_reasons:
            exclusion_reasons.append(ATS_REASON_NO_N_OVER_N)

    exclusion_reasons = [reason for reason in exclusion_reasons if reason in CANONICAL_REASONS]
    ordered_reasons: List[str] = []
    for reason in (
        ATS_REASON_NO_N_OVER_N,
        ATS_REASON_FOLLOW_UP,
        ATS_REASON_NONSPECIFIC,
        ATS_REASON_DERIVED,
    ):
        if reason in exclusion_reasons and reason not in ordered_reasons:
            ordered_reasons.append(reason)

    blockers = {reason for reason in ordered_reasons if reason != ATS_REASON_NO_N_OVER_N}
    has_counts = numerator is not None and denominator is not None
    compatible = has_counts and counts_adjacent and not blockers

    diagnostic.strict = bool(compatible)
    diagnostic.compatible_with_ats = bool(compatible)
    diagnostic.exclusion_reasons = ordered_reasons

    result["strict_yield_detected"] = bool(initial_strict_claim or strict_indices or has_counts)
    result["compatible"] = diagnostic.compatible_with_ats
    result["exclusion_reasons"] = ordered_reasons

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


def _ordered_paragraphs(paragraph_store: Dict[str, Dict[str, object]]) -> List[Tuple[int, Optional[int], str]]:
    ordered: List[Tuple[int, Optional[int], str]] = []
    for entry in paragraph_store.values():
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        orders = entry.get("order") or []
        try:
            order_index = min(int(value) for value in orders) if orders else 10**6
        except (TypeError, ValueError):
            order_index = 10**6
        page = entry.get("page")
        ordered.append((order_index, page, text.lower()))
    ordered.sort(key=lambda item: item[0])
    return ordered


def _strict_anchor_indices(paragraphs: List[Tuple[int, Optional[int], str]]) -> List[int]:
    indices: List[int] = []
    for idx, (_order, _page, text) in enumerate(paragraphs):
        if "strict" in text:
            indices.append(idx)
    return indices


def _anchors_have_adjacent_counts(
    paragraphs: List[Tuple[int, Optional[int], str]],
    indices: List[int],
) -> bool:
    if not paragraphs or not indices:
        return True

    for anchor_idx in indices:
        text = paragraphs[anchor_idx][2]
        if N_OVER_N_PATTERN.search(text):
            return True
        neighbors = []
        if anchor_idx > 0:
            neighbors.append(paragraphs[anchor_idx - 1][2])
        if anchor_idx + 1 < len(paragraphs):
            neighbors.append(paragraphs[anchor_idx + 1][2])
        for neighbor_text in neighbors:
            if neighbor_text and N_OVER_N_PATTERN.search(neighbor_text):
                return True
    return False


__all__ = ["validate_ats_yield"]
