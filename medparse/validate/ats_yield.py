"""ATS diagnostic yield validation helpers."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from medparse.schema.article import ArticleDocument, ATSCompatibility
from medparse.normalize._ats_codes import (
    ATS_REASON_NO_N_OVER_N,
    ATS_REASON_FOLLOW_UP,
    ATS_REASON_NONSPECIFIC,
    ATS_REASON_DERIVED,
    ATS_CANONICAL_REASONS,
    canonicalize_reason,
)
from medparse.validate.applicability import is_diagnostic_study

FOLLOW_UP_PATTERN = re.compile(r"\b12[-\s]*month diagnostic yield\b", re.IGNORECASE)
FOLLOW_UP_CONSIDERED_PATTERN = re.compile(r"considered diagnostic if follow[-\s]*up", re.IGNORECASE)
INTERMEDIATE_PATTERN = re.compile(r"\b(intermediate|liberal)\s+diagnostic\s+yield\b", re.IGNORECASE)
NONSPECIFIC_TERMS = re.compile(r"\b(atypia|suspicious|nonspecific)\b", re.IGNORECASE)
N_OVER_N_PATTERN = re.compile(r"\b\d{1,4}\s*/\s*\d{1,4}\b")


def _append_reason(reasons: List[str], reason: str) -> None:
    if not reason:
        return
    if reason not in reasons:
        reasons.append(reason)


def validate_ats_yield(document: ArticleDocument) -> Dict[str, object]:
    """Validate diagnostic yield fields against ATS strict semantics."""

    result = {
        "strict_yield_detected": False,
        "compatible": True,
        "exclusion_reasons": [],
    }

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    ats_compat = getattr(document, "ats_compatibility", None)
    if not isinstance(ats_compat, ATSCompatibility):
        ats_compat = ATSCompatibility()
        document.ats_compatibility = ats_compat

    subtype = (getattr(document, "doc_subtype", None) or "").strip().lower()
    scope = (
        getattr(document, "research_scope", None)
        or pipeline_info.get("research_scope")
        if isinstance(pipeline_info, dict)
        else None
    )
    scope_normalized = str(scope or "").strip().lower()
    if not scope_normalized and subtype == "research_diagnostic":
        scope_normalized = "diagnostic_ppn_bronchoscopy"
    strict_candidate = scope_normalized == "diagnostic_ppn_bronchoscopy"
    if not strict_candidate:
        pipeline_info["ats_yield_applicability"] = "not_applicable"
        reasons: List[str] = []
        if scope_normalized:
            reasons.append(f"research_scope:{scope_normalized}")
        if subtype:
            reasons.append(f"doc_subtype:{subtype}")
        if "not_diagnostic_study" not in reasons:
            reasons.append("not_diagnostic_study")
        pipeline_info["ats_yield_reasons"] = reasons
        ats_compat.strict_required = False
        ats_compat.compatible_with_ats = False
        _append_reason(ats_compat.exclusion_reasons, "not_diagnostic_study")
        document.pipeline_info = pipeline_info
        result["strict_yield_detected"] = False
        result["compatible"] = False
        result["exclusion_reasons"] = ["not_diagnostic_study"]
        return result

    diagnostic = getattr(document, "diagnostic_yield", None)
    if diagnostic is None:
        pipeline_info["ats_yield_applicability"] = pipeline_info.get("ats_yield_applicability", "not_applicable")
        pipeline_info.setdefault("ats_yield_reasons", ["no_diagnostic_payload"])
        document.pipeline_info = pipeline_info
        result["compatible"] = False
        return result

    applicability, applicability_reasons = is_diagnostic_study(document)
    if applicability:
        pipeline_info["ats_yield_applicability"] = "applicable"
    else:
        pipeline_info["ats_yield_applicability"] = "not_applicable"
        pipeline_info["ats_yield_reasons"] = applicability_reasons
        document.pipeline_info = pipeline_info
        result["strict_yield_detected"] = False
        result["compatible"] = False
        result["exclusion_reasons"] = []
        return result
    ats_compat.strict_required = True if applicability else False
    ats_compat.compatible_with_ats = bool(applicability)
    if applicability:
        ats_compat.exclusion_reasons = []
    if not applicability:
        reasons_block = list(applicability_reasons or [])
        for reason in reasons_block:
            _append_reason(ats_compat.exclusion_reasons, reason)
        _append_reason(ats_compat.exclusion_reasons, "not_diagnostic_study")
        if "not_diagnostic_study" not in reasons_block:
            reasons_block.append("not_diagnostic_study")
        pipeline_info["ats_yield_reasons"] = reasons_block
        document.pipeline_info = pipeline_info
        result["strict_yield_detected"] = False
        result["compatible"] = False
        result["exclusion_reasons"] = ["not_diagnostic_study"]
        return result

    pipeline_info["ats_yield_reasons"] = applicability_reasons or ["diagnostic_cues_detected"]
    document.pipeline_info = pipeline_info

    paragraph_store = getattr(document, "paragraph_store", {}) or {}
    ordered_paragraphs = _ordered_paragraphs(paragraph_store)
    texts = [text for _order, _page, text in ordered_paragraphs]

    initial_strict_claim = bool(getattr(diagnostic, "strict", False) or getattr(diagnostic, "compatible_with_ats", False))

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    warnings_bucket = pipeline_info.setdefault("warnings", [])
    if not isinstance(warnings_bucket, list):
        warnings_bucket = pipeline_info["warnings"] = list(warnings_bucket) if isinstance(warnings_bucket, (list, tuple)) else []

    exclusion_reasons: List[str] = []
    for reason in diagnostic.exclusion_reasons or []:
        normalized = canonicalize_reason(reason)
        if normalized:
            if normalized not in exclusion_reasons:
                exclusion_reasons.append(normalized)
            if normalized != reason and reason is not None:
                message = f"ATS diagnostic yield reason normalized to '{normalized}' from '{reason}'."
                if message not in warnings_bucket:
                    warnings_bucket.append(message)
            continue
        if reason and reason not in ATS_CANONICAL_REASONS:
            message = f"ATS diagnostic yield reason '{reason}' not recognized; dropped."
            if message not in warnings_bucket:
                warnings_bucket.append(message)

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

    exclusion_reasons = [reason for reason in exclusion_reasons if reason in ATS_CANONICAL_REASONS]
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
    document.pipeline_info = pipeline_info

    return result


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
