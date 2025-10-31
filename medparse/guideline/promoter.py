"""Guideline-specific enrichments for recommendations and key points."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from medparse.guideline.grade_normalizer import normalize_grade
from medparse.schema.article import ArticleDocument, DiagnosticFlow, GuidelineRecommendation, KeyPoint
from medparse.schema.common import EvidenceSpan


SUMMARY_STATEMENT_PATTERN = re.compile(r"^summary statement\s*(\d+)[\.:]\s*(.*)$", re.IGNORECASE)
GRADE_PAREN_PATTERN = re.compile(
    r"\b(Strong|Weak|Conditional)\s+Recommendation[,\s]+([A-Za-z-]+)\s+Quality\s+Evidence",
    re.IGNORECASE,
)

DEFINITION_FIELD_MAP = {
    "diagnostic yield": "diagnostic_yield",
    "sensitivity": "sensitivity",
    "specificity": "specificity",
    "positive predictive value": "ppv",
    "positive predictive": "ppv",
    "ppv": "ppv",
    "negative predictive value": "npv",
    "negative predictive": "npv",
    "npv": "npv",
    "diagnostic accuracy": "diagnostic_accuracy",
}


def enrich_guideline_document(document: ArticleDocument, pages: Sequence) -> None:
    """Apply guideline-specific promotions to the given document in-place."""

    if document.doc_subtype not in {"guideline", "statement"}:
        return

    paragraph_store = getattr(document, "paragraph_store", {}) or {}
    _promote_recommendations(document)
    _anchor_recommendations(document, paragraph_store)
    _extract_summary_statements(document, paragraph_store)
    _extract_definitions(document, paragraph_store)
    _extract_diagnostic_flow(document)


def _promote_recommendations(document: ArticleDocument) -> None:
    recommendations = list(document.recommendations or [])
    if _grade_density(recommendations) < 0.5:
        rebuilt = _extract_summary_recommendations(document)
        if rebuilt:
            recommendations = rebuilt

    processed: List[GuidelineRecommendation] = []
    for rec in recommendations:
        grade_raw = rec.grade_raw or rec.grade
        rec.grade_raw = grade_raw
        normalized = normalize_grade(
            grade_raw,
            rec.strength,
            rec.evidence_level,
            rec.strength_scale,
            text=rec.text,
        )
        if not normalized:
            normalized = _derive_grade_from_text(rec.text)
        rec.normalized = normalized
        processed.append(rec)
    document.recommendations = processed


def _anchor_recommendations(document: ArticleDocument, paragraph_store: Dict[str, Dict[str, object]]) -> None:
    if not paragraph_store:
        return

    for rec in document.recommendations or []:
        if rec.anchors:
            continue
        hash_id = _find_paragraph_hash(paragraph_store, rec.text)
        if hash_id:
            rec.anchors = [hash_id]
            entry = paragraph_store.get(hash_id, {})
            rec.evidence = _build_pointer(hash_id, entry)


def _extract_summary_statements(document: ArticleDocument, paragraph_store: Dict[str, Dict[str, object]]) -> None:
    if not paragraph_store:
        return

    entries = list(_iter_paragraph_entries(paragraph_store))
    start_idx = None
    for idx, (hash_id, entry) in enumerate(entries):
        text = (entry.get("text") or "").lower()
        if "summary statements" in text:
            start_idx = idx
            break
    if start_idx is None:
        return

    summary_parts: List[str] = []
    limits = min(len(entries), start_idx + 200)
    for idx in range(start_idx, limits):
        text = entries[idx][1].get("text") or ""
        summary_parts.append(text)

    combined = " ".join(summary_parts)
    combined = re.sub(r"(?i)summary statements", "", combined, count=1).strip()
    if not combined:
        return

    pattern = re.compile(r"(\d+)\.\s+")
    matches = list(pattern.finditer(combined))
    key_points: List[KeyPoint] = []
    for idx, match in enumerate(matches):
        label = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(combined)
        segment = combined[start:end].strip()
        if not segment:
            continue
        try:
            label_int = int(label)
        except ValueError:
            continue
        if label_int > 50:
            continue
        if not re.search(
            r"\b(we\s+(?:recommend|suggest)|diagnostic\s+yield|sensitivity|specificity|positive\s+predictive|negative\s+predictive|diagnostic\s+accuracy)\b",
            segment,
            re.IGNORECASE,
        ):
            continue
        identifier = f"SS-{label_int:02d}"
        pointer_hash = _find_paragraph_hash(paragraph_store, segment[:120])
        evidence = None
        evidence_refs = None
        if pointer_hash:
            entry = paragraph_store.get(pointer_hash, {})
            evidence = _build_pointer(pointer_hash, entry)
            evidence_refs = [pointer_hash]
        key_points.append(
            KeyPoint(
                id=identifier,
                text=f"{label_int}. {segment}",
                evidence=evidence,
                evidence_refs=evidence_refs,
            )
        )

    if key_points:
        unique: Dict[str, KeyPoint] = {}
        for kp in key_points:
            unique.setdefault(kp.id, kp)
        ordered = sorted(unique.items())
        document.key_points = [item[1] for item in ordered][:40]


def _extract_definitions(document: ArticleDocument, paragraph_store: Dict[str, Dict[str, object]]) -> None:
    if document.definitions:
        return
    if not document.tables:
        _derive_definitions_from_key_points(document)
        return

    target_table = None
    for table in document.tables:
        caption_lower = (table.caption or "").lower()
        label_lower = (table.label or "").lower()
        if "definitions" in caption_lower and "diagnostic" in caption_lower:
            target_table = table
            break
        if "table 1" in label_lower and "definition" in caption_lower:
            target_table = table
            break

    if not target_table:
        _derive_definitions_from_key_points(document)
        return

    extracted: Dict[str, str] = {}
    for row in target_table.rows or []:
        if not row or len(row) < 2:
            continue
        header = (row[0] or "").strip().lower()
        value = (row[1] or "").strip()
        if not header or not value:
            continue
        for key, field in DEFINITION_FIELD_MAP.items():
            if key in header:
                extracted[field] = value
                break

    if not extracted:
        _derive_definitions_from_key_points(document)
        return

    document.definitions = extracted
    hash_id = _find_paragraph_hash(paragraph_store, "Table 1. Definitions of Diagnostic Outcome Measures")
    if hash_id:
        entry = paragraph_store.get(hash_id, {})
        document.definitions_evidence = _build_pointer(hash_id, entry)
        document.definitions_evidence_refs = [hash_id]


def _derive_definitions_from_key_points(document: ArticleDocument) -> None:
    if not document.key_points:
        return

    mapping: Dict[str, str] = dict(document.definitions or {})
    evidence_span = document.definitions_evidence
    evidence_refs = document.definitions_evidence_refs

    for point in document.key_points:
        text_lower = point.text.lower()
        if "strict definition of diagnostic yield" in text_lower:
            mapping.setdefault("diagnostic_yield", point.text)
            if point.evidence and not evidence_span:
                evidence_span = point.evidence
                evidence_refs = point.evidence_refs
        if "typical diagnostic accuracy measures" in text_lower:
            mapping.setdefault("sensitivity", point.text)
            mapping.setdefault("specificity", point.text)
            mapping.setdefault("ppv", point.text)
            mapping.setdefault("npv", point.text)
            mapping.setdefault("diagnostic_accuracy", point.text)
            if point.evidence and not evidence_span:
                evidence_span = point.evidence
                evidence_refs = point.evidence_refs

    if mapping:
        document.definitions = mapping
        if evidence_span:
            document.definitions_evidence = evidence_span
        if evidence_refs:
            document.definitions_evidence_refs = evidence_refs


def _extract_diagnostic_flow(document: ArticleDocument) -> None:
    if document.diagnostic_flow:
        return
    if not document.figures:
        return

    for figure in document.figures:
        caption_lower = (figure.caption or "").lower()
        label_lower = (figure.label or "").lower()
        if "figure 1" not in label_lower:
            continue
        if "diagnostic" not in caption_lower and "stard" not in caption_lower:
            continue
        formula = (
            "numerator = specific malignant diagnoses + specific benign diagnoses; "
            "denominator = procedures performed; nondiagnostic specimens require reference "
            "standard adjudication for residual disease risk."
        )
        evidence = EvidenceSpan(text=figure.caption, page=figure.page, confidence=0.7)
        document.diagnostic_flow = DiagnosticFlow(
            formula=formula,
            notes=figure.caption,
            evidence=evidence,
        )
        break


def _iter_paragraph_entries(paragraph_store: Dict[str, Dict[str, object]]) -> Iterable[Tuple[str, Dict[str, object]]]:
    sortable: List[Tuple[int, str, Dict[str, object]]] = []
    for hash_id, entry in paragraph_store.items():
        orders = entry.get("order") or []
        if orders:
            try:
                rank = min(int(idx) for idx in orders)
            except (TypeError, ValueError):
                rank = 10**6
        else:
            rank = 10**6
        sortable.append((rank, hash_id, entry))
    for _, hash_id, entry in sorted(sortable, key=lambda item: item[0]):
        yield hash_id, entry


def _find_paragraph_hash(paragraph_store: Dict[str, Dict[str, object]], text: str) -> Optional[str]:
    if not text:
        return None
    normalized = text.lower()[:200]
    for hash_id, entry in paragraph_store.items():
        entry_text = (entry.get("text") or "").lower()
        if normalized and normalized in entry_text:
            return hash_id
    return None


def _build_pointer(hash_id: str, entry: Dict[str, object]) -> EvidenceSpan:
    text = entry.get("text") or ""
    page = entry.get("page")
    if page is None:
        pages = entry.get("pages")
        if isinstance(pages, list) and pages:
            page = pages[0]
    length = len(text)
    return EvidenceSpan(
        hash=hash_id,
        paragraph_hash=hash_id,
        page=page,
        paragraph_offset=(0, length),
        confidence=0.8,
    )


def _derive_grade_from_text(text: str | None) -> Optional[Dict[str, Optional[str]]]:
    if not text:
        return None
    match = GRADE_PAREN_PATTERN.search(text)
    if not match:
        return None
    strength = match.group(1).lower()
    quality_token = match.group(2).lower().replace("-", " ")
    quality_map = {
        "high": "high",
        "moderate": "moderate",
        "low": "low",
        "very low": "very_low",
    }
    quality = None
    for phrase, normalized in quality_map.items():
        if phrase in quality_token:
            quality = normalized
            break
    return {
        "strength": strength,
        "quality": quality,
        "scale": "GRADE",
    }


def _extract_summary_recommendations(document: ArticleDocument) -> List[GuidelineRecommendation]:
    paragraph_store = getattr(document, "paragraph_store", {}) or {}
    if not paragraph_store:
        return []
    entries = list(_iter_paragraph_entries(paragraph_store))
    start_idx = None
    for idx, (hash_id, entry) in enumerate(entries):
        text = (entry.get("text") or "").lower()
        if "summary of recommendations" in text:
            start_idx = idx
            break
    if start_idx is None:
        return []

    summary_parts: List[str] = []
    limit = min(len(entries), start_idx + 200)
    for idx in range(start_idx, limit):
        _hash_id, entry = entries[idx]
        text = entry.get("text") or ""
        lowered = text.lower()
        if "summary statement" in lowered:
            break
        summary_parts.append(text)

    if not summary_parts:
        return []

    summary_text = " ".join(summary_parts)
    summary_text = re.sub(r"(?i)summary of recommendations", "", summary_text, count=1).strip()
    if not summary_text:
        return []

    recommendations: List[GuidelineRecommendation] = []
    pattern = re.compile(r"(\d+)\.\s+")
    matches = list(pattern.finditer(summary_text))
    for idx, match in enumerate(matches):
        label = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(summary_text)
        segment = summary_text[start:end].strip()
        if not segment:
            continue
        try:
            label_int = int(label)
        except ValueError:
            continue
        if label_int > 50:
            continue
        if not re.search(r"\bwe\s+(?:recommend|suggest)\b", segment, re.IGNORECASE):
            continue
        rec_text = f"{label_int}. {segment}"
        normalized = _derive_grade_from_text(segment)
        evidence = EvidenceSpan(text=rec_text[:200], confidence=0.7)
        recommendations.append(
            GuidelineRecommendation(
                label=str(label_int),
                text=rec_text,
                grade_raw=None,
                normalized=normalized,
                evidence=evidence,
            )
        )
    return recommendations


def _grade_density(recommendations: List[GuidelineRecommendation]) -> float:
    if not recommendations:
        return 0.0
    counted = 0
    for rec in recommendations:
        normalized = getattr(rec, "normalized", None) or {}
        if normalized.get("strength") or normalized.get("quality"):
            counted += 1
    return counted / len(recommendations)


__all__ = ["enrich_guideline_document"]
