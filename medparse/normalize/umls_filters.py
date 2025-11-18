"""Filtering and calibration helpers for linked UMLS entities."""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from medparse.normalize.umls_linking import UmlsEntity

SHORT_TEXT_WHITELIST = {"IPF", "NSIP", "COPD", "EBUS", "EUS", "LDCT", "HRCT", "ATS", "CT"}
MONTH_NAMES = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}
STOPWORD_TERMS = {
    "table",
    "figure",
    "page",
    "md",
    "dr",
    "mr",
    "mrs",
    "ms",
    "prof",
}
GUIDELINE_ALLOWED_SEMTYPES = {"T047", "T061", "T184", "T080", "T200"}
GUIDELINE_SUBTYPES = {"guideline", "statement"}
DRUG_SEMTYPES = {"T109", "T121", "T195", "T200"}
TREATMENT_CUES = {
    "treat",
    "therapy",
    "therapies",
    "therapeutic",
    "dose",
    "dosed",
    "dosage",
    "administer",
    "pharmacologic",
    "drug",
    "medication",
}


FilterReport = Dict[str, object]


def filter_umls_entities(
    entities: Sequence[UmlsEntity],
    *,
    page_texts: Optional[Dict[int, str]] = None,
    doc_subtype: Optional[str] = None,
) -> Tuple[List[UmlsEntity], FilterReport]:
    """Filter UMLS entities down to high-precision mentions.

    Args:
        entities: Raw linked entities from the linker
        page_texts: Optional mapping of page number to raw text for context
        doc_subtype: Article subtype (e.g., ``guideline``)

    Returns:
        Tuple of (kept_entities, filtering_report)
    """

    if not entities:
        return [], {"kept": 0, "dropped": {}}

    page_map = page_texts or {}
    kept: List[UmlsEntity] = []
    dropped_reasons: Counter[str] = Counter()
    dropped_samples: List[Dict[str, object]] = []
    downranked = 0
    subtype = (doc_subtype or "").strip().lower()
    is_guideline = subtype in GUIDELINE_SUBTYPES

    for entity in entities:
        reason = _drop_reason(entity, page_map, is_guideline)
        if reason:
            dropped_reasons[reason] += 1
            if len(dropped_samples) < 8:
                dropped_samples.append(
                    {
                        "cui": entity.cui,
                        "text": entity.text,
                        "reason": reason,
                    }
                )
            continue

        if is_guideline and _needs_drug_downrank(entity, page_map):
            entity.confidence = round(max(0.05, entity.confidence * 0.65), 4)
            downranked += 1

        kept.append(entity)

    report: FilterReport = {"kept": len(kept), "dropped": dict(dropped_reasons)}
    if dropped_samples:
        report["examples"] = dropped_samples
    if downranked:
        report["downranked"] = downranked
    return kept, report


def _drop_reason(entity: UmlsEntity, page_map: Dict[int, str], is_guideline: bool) -> Optional[str]:
    text = (entity.text or "").strip()
    if not text:
        return "empty_text"

    normalized_alpha = re.sub(r"[^a-z]", "", text.lower())
    if normalized_alpha in MONTH_NAMES or normalized_alpha in STOPWORD_TERMS:
        return "stop_term"
    prefix = re.sub(r"[^a-z]", "", text.lower())
    if any(prefix.startswith(marker) for marker in ("table", "figure", "page")):
        return "stop_term"

    if len(text) < 4 and text.upper() not in SHORT_TEXT_WHITELIST:
        return "short_text"

    if not _is_token_aligned(entity, page_map):
        return "misaligned_span"

    if is_guideline:
        semtypes = {token.upper() for token in entity.semtypes}
        if not semtypes:
            return "guideline_semtype"
        if semtypes.isdisjoint(GUIDELINE_ALLOWED_SEMTYPES) and semtypes.isdisjoint(DRUG_SEMTYPES):
            return "guideline_semtype"

    return None


def _needs_drug_downrank(entity: UmlsEntity, page_map: Dict[int, str]) -> bool:
    semtypes = {token.upper() for token in entity.semtypes}
    if not semtypes or not semtypes.intersection(DRUG_SEMTYPES):
        return False
    if _has_treatment_context(entity, page_map):
        return False
    return True


def _is_token_aligned(entity: UmlsEntity, page_map: Dict[int, str]) -> bool:
    if not entity.offsets or not entity.page:
        return True
    text = page_map.get(entity.page) or ""
    if not text:
        return True
    entity_text = (entity.text or "").strip().lower()
    for start, end in entity.offsets:
        if start is None or end is None or start < 0 or end <= start:
            continue
        if start >= len(text):
            continue
        start_char = text[start]
        end_index = min(end, len(text)) - 1
        end_char = text[end_index]
        span = text[start:end].strip().lower()
        enforce_boundaries = bool(entity_text and span and span == entity_text)
        if enforce_boundaries:
            if start > 0 and text[start - 1].isalnum() and start_char.isalnum():
                return False
            if end < len(text) and text[end].isalnum() and end_char.isalnum():
                return False
    return True


def _has_treatment_context(entity: UmlsEntity, page_map: Dict[int, str], window: int = 64) -> bool:
    if not entity.page or not entity.offsets:
        return False
    text = page_map.get(entity.page)
    if not text:
        return False
    start, end = entity.offsets[0]
    if start is None or end is None:
        return False
    start = max(0, start - window)
    end = min(len(text), end + window)
    context = text[start:end].lower()
    return any(cue in context for cue in TREATMENT_CUES)


__all__ = ["filter_umls_entities"]
