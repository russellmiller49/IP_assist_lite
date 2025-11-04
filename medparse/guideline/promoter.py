"""Guideline-specific enrichments for recommendations and key points."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple

from medparse.normalize.guideline_grade import SIGN_INLINE_RE, detect_context_candidates, detect_inline_candidates
from medparse.tables.extract_guideline_tables import TableGradeIndex, extract_guideline_grade_index
from medparse.guideline.grades import canonicalize_scale, map_grade_code, map_sign_letter
from medparse.schema.article import ArticleDocument, DiagnosticFlow, GuidelineRecommendation, KeyPoint
from medparse.schema.common import EvidenceSpan


SUMMARY_STATEMENT_PATTERN = re.compile(r"^summary statement\s*(\d+)[\.:]\s*(.*)$", re.IGNORECASE)
CHEST_UNGRADED_PATTERN = re.compile(r"Ungraded\s+Consensus-?Based\s+Statement", re.IGNORECASE)
REMARK_PATTERN = re.compile(r"Remarks:\s*(.+?)(?=(?:Remarks:)|$)", re.IGNORECASE | re.DOTALL)
SUMMARY_HEADING_PATTERNS = [
    re.compile(r"^summary\s+of\s+recommendations[\.:]?$", re.IGNORECASE),
    re.compile(r"^summary\s+of\s+recommendations\s+and\s+conclusions[\.:]?$", re.IGNORECASE),
]
ITEM_SPLIT_PATTERN = re.compile(r"(\d{1,2})\.\s+")
GRADE_NEIGHBOR_HINT = re.compile(
    r"(?i)\b(recommendation\s+grade|strong\s+recommendation|conditional\s+recommendation|certainty|quality|ucs|consensus)\b"
)
JOIN_PUNCTUATION = {":", ";", ",", "—", "-", "–"}
RECOMMENDATION_VERB = re.compile(r"(?i)\bwe\s+(recommend|suggest)\b")
RECOMMENDATION_MODAL = re.compile(r"(?i)\b(we\s+(?:recommend|suggest)|recommend(?:ation|ations)?|suggest(?:ion|ions)?)\b")
GRADE_PAREN_PHRASE_RE = re.compile(
    r"\(\s*(?:grade\s*[12]\s*[ABCD]|(?:strong|conditional|weak)\s+recommendation[^)]{0,120}|ungraded\s+consensus(?:-?based)?\s+statement)\s*\)",
    re.IGNORECASE,
)
GRADE_CODE_INLINE_RE = re.compile(r"(?i)\bgrade\s*(?:recommendation\s*)?([12])\s*([ABCD])\b")
ATS_WORD_RE = re.compile(r"\bats\b")

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


class EnumeratedItem(NamedTuple):
    number: str
    text: str
    paragraph_hashes: List[str]


def _has_numbered_recap(document: ArticleDocument) -> bool:
    sections = getattr(document, "sections", {}) or {}
    for key, value in sections.items():
        if not isinstance(value, str) or not value:
            continue
        lowered_key = str(key or "").lower()
        if any(token in lowered_key for token in ("recommendation", "summary", "statement")):
            if re.search(r"\b\d+\.\s", value):
                return True
    return False


def _infer_grade_scale_hint(document: ArticleDocument) -> Optional[str]:
    """Infer the dominant grading scheme from document metadata."""

    fields: List[str] = []
    for attr in ("title", "journal"):
        value = getattr(document, attr, None)
        if isinstance(value, str) and value.strip():
            fields.append(value)
    source_file = getattr(document, "source_file", None)
    if isinstance(source_file, str) and source_file.strip():
        fields.append(source_file)
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if isinstance(pipeline_info, dict):
        front_matter = pipeline_info.get("front_matter")
        if isinstance(front_matter, dict):
            for value in front_matter.values():
                if isinstance(value, str) and value.strip():
                    fields.append(value)

    combined = " ".join(part for part in fields if part).lower()
    if not combined:
        return None
    if "chest" in combined or "american college of chest physicians" in combined or "accp" in combined:
        return "CHEST"
    if "esge" in combined or ("ers" in combined and "ests" in combined):
        return "ESGE_ERS_ESTS"
    if "american thoracic society" in combined or ATS_WORD_RE.search(combined):
        return "ATS_ERS"
    return None


def enrich_guideline_document(document: ArticleDocument, pages: Sequence) -> None:
    """Apply guideline-specific promotions to the given document in-place."""

    subtype = (getattr(document, "doc_subtype", "") or "").strip().lower()
    eligible = False
    if subtype:
        if "guideline" in subtype or "statement" in subtype or subtype == "classification":
            eligible = True
    if not eligible and _has_numbered_recap(document):
        eligible = True
    if not eligible:
        return

    paragraph_store = getattr(document, "paragraph_store", {}) or {}
    _promote_recommendations(document, paragraph_store)
    _anchor_recommendations(document, paragraph_store)
    _extract_summary_statements(document, paragraph_store)
    _ensure_statement_key_points(document, paragraph_store)
    _extract_definitions(document, paragraph_store)
    _extract_diagnostic_flow(document)


def _promote_recommendations(document: ArticleDocument, paragraph_store: Dict[str, Dict[str, object]]) -> None:
    summary_recs = _extract_summary_recommendations(document, paragraph_store)
    base_recs = list(document.recommendations or [])

    recommendations: List[GuidelineRecommendation] = []
    seen_signatures: Set[str] = set()

    for rec in base_recs:
        if not isinstance(rec, GuidelineRecommendation) or not rec.text:
            continue
        signature = _stable_text_signature(rec.text)
        if signature in seen_signatures:
            continue
        recommendations.append(rec)
        seen_signatures.add(signature)

    for rec in summary_recs or []:
        if not isinstance(rec, GuidelineRecommendation) or not rec.text:
            continue
        signature = _stable_text_signature(rec.text)
        if signature in seen_signatures:
            continue
        recommendations.append(rec)
        seen_signatures.add(signature)

    pending_remarks = _preprocess_recommendations(recommendations)
    grade_sources = _assign_recommendation_grades(document, recommendations, paragraph_store)
    _finalize_recommendation_texts(recommendations)
    _apply_remarks(recommendations, pending_remarks)

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if isinstance(grade_sources, dict) and grade_sources:
        metrics_block = pipeline_info.setdefault("recommendation_metrics", {})
        metrics_block["grade_source_breakdown"] = dict(grade_sources)
        pipeline_info["grade_source_breakdown"] = dict(grade_sources)
    document.pipeline_info = pipeline_info
    document.recommendations = recommendations
    _update_recommendation_metrics(document)


def _preprocess_recommendations(recommendations: List[GuidelineRecommendation]) -> Dict[int, List[str]]:
    pending_remarks: Dict[int, List[str]] = {}
    for rec in recommendations:
        original_text = rec.text or ""
        cleaned_text, remarks = _strip_remarks(original_text)
        stripped_text = cleaned_text or rec.text or ""
        stripped_text, inline_grades = _strip_inline_grade_phrases(stripped_text)
        if stripped_text:
            rec.text = stripped_text
        pending_remarks[id(rec)] = [remark.strip() for remark in (remarks or []) if remark and remark.strip()]
        rec.grade_candidates = []
        rec.grade_normalized = None
        rec.grade_source = None
        rec.normalized = None
        rec.grade = rec.grade if isinstance(rec.grade, str) else None
        grade_fragments: List[str] = []
        if rec.grade_raw:
            grade_fragments.append(str(rec.grade_raw))
        grade_fragments.extend(inline_grades)
        cleaned_fragments = [fragment.strip() for fragment in grade_fragments if fragment and fragment.strip()]
        if cleaned_fragments:
            rec.grade_raw = "; ".join(dict.fromkeys(cleaned_fragments))
        else:
            rec.grade_raw = None
        rec.ungraded = False
        rec.ungraded_reason = rec.ungraded_reason
        rec.consensus_basis = rec.consensus_basis
        rec.graded = False
        rec.typed = False
        if CHEST_UNGRADED_PATTERN.search(original_text):
            rec.consensus_basis = rec.consensus_basis or "CHEST-ungraded"
        rec.text = " ".join((rec.text or "").split())
        rec.remarks = []
    return pending_remarks


def _apply_remarks(recommendations: List[GuidelineRecommendation], remarks_map: Dict[int, List[str]]) -> None:
    for rec in recommendations:
        pending = remarks_map.get(id(rec), [])
        if pending:
            rec.remarks = pending
        elif not getattr(rec, "remarks", None):
            rec.remarks = []


def _assign_recommendation_grades(
    document: ArticleDocument,
    recommendations: List[GuidelineRecommendation],
    paragraph_store: Dict[str, Dict[str, object]],
) -> Dict[str, int]:
    tables = getattr(document, "tables", []) or []
    table_index = extract_guideline_grade_index(tables, signature_fn=_stable_text_signature)
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    summary_anchor_ids = set(pipeline_info.get("summary_recommendation_anchors") or [])
    scale_hint = _infer_grade_scale_hint(document)
    if isinstance(pipeline_info, dict) and scale_hint:
        pipeline_info.setdefault("grade_scale_hint", scale_hint)
        document.pipeline_info = pipeline_info
    context_map = _collect_context_grade_candidates(recommendations, paragraph_store)
    summary_grade_map = _collect_summary_grade_candidates(paragraph_store)
    source_counts: Dict[str, int] = defaultdict(int)
    ordered_entries = _ordered_paragraph_entries(paragraph_store) if paragraph_store else []
    entry_index = {hash_id: idx for idx, (_, hash_id, _) in enumerate(ordered_entries)}

    for rec in recommendations:
        inline_payloads = _inline_candidates_for_rec(rec, paragraph_store, ordered_entries, entry_index)
        table_payloads = _table_candidates_for_rec(rec, table_index)
        context_payloads = [dict(candidate) for candidate in context_map.get(id(rec), [])]

        summary_payloads = [dict(payload) for payload in summary_grade_map.get(rec.label or "", [])]
        combined = inline_payloads + table_payloads + context_payloads + summary_payloads
        if combined:
            combined = _deduplicate_payloads(combined)
            ordered = sorted((dict(payload) for payload in combined), key=_candidate_sort_key, reverse=True)
        else:
            ordered = []

        rec.grade_candidates = ordered
        best = ordered[0] if ordered else None
        if best and best.get("source") == "inline" and _is_summary_recommendation(rec, summary_anchor_ids):
            best["source"] = "table"
            ordered[0] = dict(best)
        if best:
            _apply_grade_payload(rec, best, scale_hint=scale_hint)
            source = str(best.get("source") or "")
            if source:
                source_counts[source] += 1
        else:
            fallback_payload = _grade_payload_from_raw(rec.grade_raw, scale_hint=scale_hint)
            if fallback_payload:
                _apply_grade_payload(rec, fallback_payload, scale_hint=scale_hint)
                source = str(fallback_payload.get("source") or "")
                if source:
                    source_counts[source] += 1
            else:
                rec.grade_normalized = None
                rec.grade_source = None
                rec.ungraded = True
                if rec.statement_type != "consensus":
                    rec.statement_type = "ungraded"
                if rec.ungraded:
                    rec.ungraded_reason = rec.ungraded_reason or "no_grade_detected"
                rec.grade = rec.grade if isinstance(rec.grade, str) else None
        _apply_recommendation_type(rec)
        _finalize_recommendation_flags(rec)

    return dict(source_counts)


def _inline_candidates_for_rec(
    rec: GuidelineRecommendation,
    paragraph_store: Dict[str, Dict[str, object]],
    ordered_entries: List[Tuple[int, str, Dict[str, object]]],
    entry_index: Dict[str, int],
) -> List[Dict[str, object]]:
    payloads: List[Dict[str, object]] = []
    seen_texts: Set[str] = set()
    detection_texts: List[str] = []
    for base_text in (rec.text, rec.grade_raw):
        normalized = (base_text or "").strip()
        if normalized:
            detection_texts.append(normalized)
    detection_texts.extend(
        _anchor_detection_texts(
            rec,
            paragraph_store,
            ordered_entries,
            entry_index,
        )
    )
    detection_texts.extend(
        _neighbor_detection_texts(
            rec,
            paragraph_store,
            ordered_entries,
            entry_index,
        )
    )
    for candidate_text in detection_texts:
        normalized = candidate_text.strip()
        lowered = normalized.lower()
        if not normalized or lowered in seen_texts:
            continue
        seen_texts.add(lowered)
        for candidate in detect_inline_candidates(normalized):
            payloads.append(candidate.to_payload())
    return payloads


def _neighbor_detection_texts(
    rec: GuidelineRecommendation,
    paragraph_store: Dict[str, Dict[str, object]],
    ordered_entries: List[Tuple[int, str, Dict[str, object]]],
    entry_index: Dict[str, int],
) -> List[str]:
    if not paragraph_store or not ordered_entries:
        return []
    extras: Set[str] = set()
    anchors = list(rec.anchors or [])
    if not anchors:
        fallback_hash = _find_paragraph_hash(paragraph_store, (rec.text or "")[:160])
        if fallback_hash:
            anchors.append(fallback_hash)
    total_entries = len(ordered_entries)
    for anchor in anchors:
        idx = entry_index.get(anchor)
        if idx is None or idx < 0 or idx >= total_entries:
            continue
        current_entry = ordered_entries[idx][2]
        current_text = str(current_entry.get("text") or "").strip()
        # Look ahead
        if idx + 1 < total_entries:
            next_entry = ordered_entries[idx + 1][2]
            next_text = str(next_entry.get("text") or "").strip()
            if next_text.startswith("(") and GRADE_NEIGHBOR_HINT.search(next_text):
                last_char = current_text.rstrip()[-1:] if current_text else ""
                if last_char in JOIN_PUNCTUATION:
                    extras.add(f"{current_text} {next_text}")
                extras.add(next_text)
        # Look behind
        if idx - 1 >= 0:
            prev_entry = ordered_entries[idx - 1][2]
            prev_text = str(prev_entry.get("text") or "").strip()
            if prev_text.startswith("(") and GRADE_NEIGHBOR_HINT.search(prev_text):
                if current_text:
                    extras.add(f"{prev_text} {current_text}")
                extras.add(prev_text)
    return sorted(extras)


def _anchor_detection_texts(
    rec: GuidelineRecommendation,
    paragraph_store: Dict[str, Dict[str, object]],
    ordered_entries: List[Tuple[int, str, Dict[str, object]]],
    entry_index: Dict[str, int],
) -> List[str]:
    if not paragraph_store or not ordered_entries:
        return []
    texts: Set[str] = set()
    anchors = list(rec.anchors or [])
    if not anchors:
        fallback_hash = _find_paragraph_hash(paragraph_store, (rec.text or "")[:160])
        if fallback_hash:
            anchors.append(fallback_hash)
    for anchor in anchors:
        idx = entry_index.get(anchor)
        if idx is None or idx < 0 or idx >= len(ordered_entries):
            continue
        entry = ordered_entries[idx][2]
        text_value = str(entry.get("text") or "").strip()
        if text_value:
            texts.add(text_value)
    return sorted(texts)


def _looks_like_recommendation_phrase(text: Optional[str]) -> bool:
    if not text:
        return False
    return bool(RECOMMENDATION_MODAL.search(text))


def _is_summary_recommendation(
    rec: GuidelineRecommendation,
    summary_anchor_ids: Set[str],
) -> bool:
    if not summary_anchor_ids:
        return False
    return any(anchor in summary_anchor_ids for anchor in (rec.anchors or []))


def _table_candidates_for_rec(rec: GuidelineRecommendation, index: TableGradeIndex) -> List[Dict[str, object]]:
    payloads: List[Dict[str, object]] = []
    label_key = (rec.label or "").strip()
    if label_key:
        for candidate in index.by_label.get(label_key, []):
            payloads.append(dict(candidate))
    signatures: Set[str] = set()
    text_variants = [rec.text or ""]
    stripped = _strip_recommendation_label(rec.text or "")
    if stripped and stripped != rec.text:
        text_variants.append(stripped)
    for variant in text_variants:
        normalized = variant.strip()
        if not normalized:
            continue
        signature = _stable_text_signature(normalized)
        if signature in signatures:
            continue
        signatures.add(signature)
        for candidate in index.by_signature.get(signature, []):
            payloads.append(dict(candidate))
    return payloads


def _collect_context_grade_candidates(
    recommendations: List[GuidelineRecommendation],
    paragraph_store: Dict[str, Dict[str, object]],
) -> Dict[int, List[Dict[str, object]]]:
    if not paragraph_store:
        return {}

    anchor_map = _build_anchor_map(recommendations, paragraph_store)
    ordered_entries = list(_ordered_paragraph_entries(paragraph_store))
    if not ordered_entries:
        return {}

    context_map: Dict[int, List[Dict[str, object]]] = {}
    current_candidates: List[Dict[str, object]] = []

    for _, hash_id, entry in ordered_entries:
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        if _looks_like_section_heading(text):
            detected = [candidate.to_payload() for candidate in detect_context_candidates(text)]
            current_candidates = _deduplicate_payloads(detected)
        recs = anchor_map.get(hash_id)
        if not recs or not current_candidates:
            continue
        ordered_candidates = sorted(
            (dict(payload) for payload in current_candidates),
            key=_candidate_sort_key,
            reverse=True,
        )
        for rec in recs:
            rec_id = id(rec)
            if rec_id in context_map:
                continue
            context_map[rec_id] = ordered_candidates
    return context_map


def _collect_summary_grade_candidates(
    paragraph_store: Dict[str, Dict[str, object]]
) -> Dict[str, List[Dict[str, object]]]:
    candidates: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    if not paragraph_store:
        return candidates
    for entry in paragraph_store.values():
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        label_match = re.match(r"^\s*(\d{1,2})\b", text)
        if not label_match:
            continue
        label = label_match.group(1)
        for match in SIGN_INLINE_RE.finditer(text):
            payload = map_sign_letter(
                match.group(1),
                source="table",
                confidence=0.84,
                raw=match.group(0),
            )
            if payload:
                candidates[label].append(payload)
        for match in GRADE_CODE_INLINE_RE.finditer(text):
            payload = map_grade_code(
                match.group(1),
                match.group(2),
                source="table",
                confidence=0.86,
                raw=match.group(0),
            )
            if payload:
                candidates[label].append(payload)
    return candidates


def _build_anchor_map(
    recommendations: List[GuidelineRecommendation],
    paragraph_store: Dict[str, Dict[str, object]],
) -> Dict[str, List[GuidelineRecommendation]]:
    anchor_map: Dict[str, List[GuidelineRecommendation]] = defaultdict(list)
    for rec in recommendations:
        anchors = list(rec.anchors or [])
        if not anchors:
            fallback_hash = _find_paragraph_hash(paragraph_store, (rec.text or "")[:160])
            if fallback_hash:
                anchors.append(fallback_hash)
                if fallback_hash not in rec.anchors:
                    rec.anchors.append(fallback_hash)
        for hash_id in anchors:
            anchor_map.setdefault(hash_id, []).append(rec)
    return anchor_map


def _ordered_paragraph_entries(
    paragraph_store: Dict[str, Dict[str, object]],
) -> List[Tuple[int, str, Dict[str, object]]]:
    ordered: List[Tuple[int, str, Dict[str, object]]] = []
    for hash_id, entry in paragraph_store.items():
        ordered.append((_entry_order(entry), hash_id, entry))
    return sorted(ordered, key=lambda item: item[0])


def _entry_order(entry: Dict[str, object]) -> int:
    orders = entry.get("order") or []
    if not isinstance(orders, list) or not orders:
        return 10**6
    values: List[int] = []
    for raw in orders:
        try:
            values.append(int(raw))
        except (TypeError, ValueError):
            continue
    return min(values) if values else 10**6


def _strip_recommendation_label(text: str) -> str:
    stripped = text.strip()
    match = re.match(r"^\s*(?:recommendation\s*)?(\d+(?:\.\d+)*)(?:[\).:-]\s*|\s+)", stripped, re.IGNORECASE)
    if match:
        return stripped[match.end():].strip()
    return stripped


def _strip_inline_grade_phrases(text: str) -> Tuple[str, List[str]]:
    if not text:
        return text, []

    phrases: List[str] = []

    def _capture(match: re.Match[str]) -> str:
        phrase = match.group(0)
        if phrase:
            cleaned = phrase.strip()
            cleaned = cleaned.strip("() ").strip()
            if cleaned:
                phrases.append(cleaned)
        return " "

    updated = GRADE_PAREN_PHRASE_RE.sub(_capture, text)

    def _capture_code(match: re.Match[str]) -> str:
        phrase = match.group(0)
        if phrase:
            cleaned = phrase.strip()
            if cleaned not in phrases:
                phrases.append(cleaned)
        return " "

    updated = GRADE_CODE_INLINE_RE.sub(_capture_code, updated)
    cleaned = re.sub(r"\s{2,}", " ", updated).strip()
    unique = list(dict.fromkeys(phrases))
    return cleaned, unique


def _deduplicate_payloads(items: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    unique: List[Dict[str, object]] = []
    seen: Set[Tuple[object, ...]] = set()
    for payload in items:
        key = (
            payload.get("scale"),
            payload.get("strength"),
            payload.get("letter"),
            payload.get("certainty"),
            payload.get("ungraded"),
            payload.get("source"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(dict(payload))
    return unique


def _candidate_sort_key(payload: Dict[str, object]) -> Tuple[float, float, float]:
    precedence_map = {"inline": 3.0, "table": 2.0, "context": 1.0}
    precedence = precedence_map.get(str(payload.get("source") or ""), 0.0)
    try:
        confidence = float(payload.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    detail = float(
        sum(1 for key in ("letter", "strength", "certainty") if payload.get(key))
    )
    return precedence, confidence, detail


def _apply_grade_payload(
    rec: GuidelineRecommendation,
    payload: Dict[str, object],
    *,
    scale_hint: Optional[str] = None,
) -> None:
    applied = dict(payload)
    raw_value = applied.get("raw")
    canonical_scale = canonicalize_scale(applied.get("scale"), raw=raw_value, hint=scale_hint)
    if canonical_scale:
        applied["scale"] = canonical_scale
    elif applied.get("scale"):
        applied["scale"] = str(applied["scale"]).upper()
    else:
        applied.pop("scale", None)

    rec.grade_normalized = applied
    rec.grade_source = str(applied.get("source") or "")
    if raw_value:
        rec.grade_raw = str(raw_value)
    scale = applied.get("scale")
    if scale:
        rec.strength_scale = str(scale)
    strength = applied.get("strength")
    certainty = applied.get("certainty")
    letter = applied.get("letter")
    code = applied.get("code")
    value_token = applied.get("value")
    if strength:
        rec.strength = strength
    if certainty:
        rec.evidence_level = certainty
    if code:
        rec.grade = code
    elif letter:
        rec.grade = letter
    elif strength:
        rec.grade = strength
    elif isinstance(value_token, str) and value_token and value_token.lower() not in {"conditional", "strong"}:
        rec.grade = value_token
    else:
        rec.grade = rec.grade if isinstance(rec.grade, str) else None
    normalized: Dict[str, object] = {}
    if scale:
        normalized["scale"] = scale
    if strength:
        normalized["strength"] = strength
    if certainty:
        normalized["quality"] = certainty
        normalized["evidence_quality"] = certainty
    if letter:
        normalized["letter"] = letter
    if code:
        normalized["code"] = code
    if value_token:
        normalized.setdefault("value", value_token)
    rec.normalized = {key: value for key, value in normalized.items() if value is not None}
    rec.ungraded = bool(applied.get("ungraded"))
    if rec.ungraded:
        rec.ungraded_reason = rec.ungraded_reason or "consensus_detected"
        rec.consensus_basis = rec.consensus_basis or str(raw_value or scale or "CONSENSUS")
        rec.statement_type = "consensus"
        if not strength:
            rec.strength = None
        rec.grade = rec.grade if code or letter else None
    else:
        rec.ungraded_reason = None
        if rec.statement_type != "consensus":
            rec.statement_type = "graded"
        if rec.consensus_basis and rec.consensus_basis == "CHEST-ungraded":
            rec.consensus_basis = None
    rec.graded = not rec.ungraded
    rec.typed = True


def _remove_parenthetical_phrase(text: str, phrase: str) -> str:
    if not text or not phrase:
        return text
    pattern = re.compile(rf"\s*\(\s*{re.escape(phrase)}\s*\)\s*")
    updated = pattern.sub(" ", text)
    if updated == text:
        updated = text.replace(phrase, " ")
    return " ".join(updated.split())


def _strip_grade_fragments(text: str, fragments: Sequence[str]) -> str:
    if not text or not fragments:
        return text
    updated = text
    for fragment in fragments:
        fragment_clean = fragment.strip()
        if not fragment_clean:
            continue
        updated = _remove_parenthetical_phrase(updated, fragment_clean)
        escaped = re.escape(fragment_clean)
        updated = re.sub(rf"\b{escaped}\b", " ", updated, flags=re.IGNORECASE)
        updated = updated.replace(fragment_clean, " ")
    return " ".join(updated.split())


def _finalize_recommendation_texts(recommendations: Sequence[GuidelineRecommendation]) -> None:
    for rec in recommendations:
        fragments: List[str] = []
        if rec.grade_raw:
            fragments.extend(part.strip() for part in str(rec.grade_raw).split(";") if part.strip())
        grade_payload = rec.grade_normalized if isinstance(rec.grade_normalized, dict) else {}
        raw_fragment = grade_payload.get("raw") if isinstance(grade_payload, dict) else None
        if raw_fragment:
            fragments.append(str(raw_fragment).strip())
        if fragments:
            rec.text = _strip_grade_fragments(rec.text or "", fragments)


def _strip_remarks(text: str) -> tuple[str, List[str]]:
    if not text:
        return "", []
    remarks: List[str] = []
    cleaned_parts: List[str] = []
    cursor = 0
    for match in REMARK_PATTERN.finditer(text):
        cleaned_parts.append(text[cursor:match.start()])
        remark_text = match.group(1) if match.groups() else ""
        remark_clean = " ".join(remark_text.split())
        if remark_clean:
            remarks.append(remark_clean)
        cursor = match.end()
    cleaned_parts.append(text[cursor:])
    cleaned_text = " ".join("".join(cleaned_parts).split())
    return cleaned_text, remarks


def _tag_ungraded_recommendation(
    rec: GuidelineRecommendation,
    *,
    basis: Optional[str],
    reason: str,
) -> None:
    rec.ungraded = True
    rec.ungraded_reason = reason
    if basis:
        rec.consensus_basis = basis
    rec.grade = None
    rec.strength = None
    rec.strength_scale = None
    rec.normalized = None
    rec.grade_normalized = None
    if rec.recommendation_type == "consensus_statement":
        rec.statement_type = "consensus"
    else:
        rec.statement_type = "ungraded"


def _apply_recommendation_type(rec: GuidelineRecommendation) -> None:
    text_lower = (rec.text or "").lower()
    if "recommend" in text_lower:
        rec.recommendation_type = "recommendation"
    elif "suggest" in text_lower:
        rec.recommendation_type = "suggestion"
    else:
        rec.recommendation_type = rec.recommendation_type or "consensus_statement"


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
    for idx, (_hash_id, entry) in enumerate(entries):
        text = (entry.get("text") or "").strip()
        if SUMMARY_STATEMENT_PATTERN.match(text):
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
        return

    if getattr(document, "doc_subtype", None) == "statement":
        fallback_points: List[KeyPoint] = []
        seen_ids: set[str] = set()
        for hash_id, entry in entries[:60]:
            text = (entry.get("text") or "").strip()
            if not text:
                continue
            match = re.match(r"^(\d+)[\).\s]+", text)
            if not match or len(text.split()) < 6:
                continue
            label_int = int(match.group(1))
            identifier = f"SS-{label_int:02d}"
            if identifier in seen_ids:
                continue
            pointer_hash = hash_id
            evidence = _build_pointer(pointer_hash, entry)
            fallback_points.append(
                KeyPoint(
                    id=identifier,
                    text=text,
                    evidence=evidence,
                    evidence_refs=[pointer_hash],
                )
            )
            seen_ids.add(identifier)
            if len(fallback_points) >= 40:
                break
        if fallback_points:
            document.key_points = fallback_points
            return

    if not getattr(document, "key_points", None):
        fallback_points: List[KeyPoint] = []
        seen_labels: set[str] = set()
        for hash_id, entry in entries[:150]:
            text = (entry.get("text") or "").strip()
            match = re.match(r"^(\d{1,2})\.\s+(.+)", text)
            if not match:
                continue
            label = match.group(1)
            if label in seen_labels:
                continue
            seen_labels.add(label)
            segment = match.group(2).strip()
            if len(segment.split()) < 6:
                continue
            identifier = f"SS-{int(label):02d}"
            evidence = _build_pointer(hash_id, entry)
            fallback_points.append(
                KeyPoint(
                    id=identifier,
                    text=text,
                    evidence=evidence,
                    evidence_refs=[hash_id],
                )
            )
            if len(fallback_points) >= 20:
                break
        if fallback_points:
            document.key_points = fallback_points


def _ensure_statement_key_points(document: ArticleDocument, paragraph_store: Dict[str, Dict[str, object]]) -> None:
    if getattr(document, "doc_subtype", None) != "statement":
        return
    if document.key_points:
        return

    entries = list(_iter_paragraph_entries(paragraph_store))
    if not entries:
        return

    fallback_points: List[KeyPoint] = []
    seen_labels: set[str] = set()
    for hash_id, entry in entries[:200]:
        text = (entry.get("text") or "").strip()
        match = re.match(r"^(\d{1,2})\.\s+(.+)", text)
        if not match:
            continue
        label = match.group(1)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        segment = match.group(2).strip()
        if len(segment.split()) < 6:
            continue
        evidence = _build_pointer(hash_id, entry)
        fallback_points.append(
            KeyPoint(
                id=f"SS-{int(label):02d}",
                text=text,
                evidence=evidence,
                evidence_refs=[hash_id],
            )
        )
        if len(fallback_points) >= 20:
            break

    if fallback_points:
        document.key_points = fallback_points


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


def _extract_summary_recommendations(
    document: ArticleDocument,
    paragraph_store: Dict[str, Dict[str, object]],
) -> List[GuidelineRecommendation]:
    if not paragraph_store:
        return []

    entries = list(_iter_paragraph_entries(paragraph_store))
    heading_index = _locate_summary_heading(entries)
    if heading_index is None:
        return []

    items = list(_collect_enumerated_items(entries, heading_index))
    if not items:
        return []

    recommendations: List[GuidelineRecommendation] = []
    summary_anchor_ids: Set[str] = set()
    for item in items:
        recommendation = _build_recommendation_from_item(document, item, paragraph_store)
        if recommendation:
            summary_anchor_ids.update(recommendation.anchors or [])
            recommendations.append(recommendation)
    if summary_anchor_ids:
        pipeline_info = getattr(document, "pipeline_info", {}) or {}
        anchors = list(dict.fromkeys(summary_anchor_ids))
        pipeline_info.setdefault("summary_recommendation_anchors", anchors)
        document.pipeline_info = pipeline_info
    return recommendations


def _locate_summary_heading(entries: List[Tuple[str, Dict[str, object]]]) -> Optional[int]:
    for idx, (_hash_id, entry) in enumerate(entries):
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        for pattern in SUMMARY_HEADING_PATTERNS:
            if pattern.match(text):
                return idx
    return None


def _collect_enumerated_items(
    entries: List[Tuple[str, Dict[str, object]]],
    heading_index: int,
) -> List[EnumeratedItem]:
    items: List[EnumeratedItem] = []
    current_number: Optional[str] = None
    current_parts: List[str] = []
    current_paragraphs: List[str] = []
    enumerating = False
    blank_streak = 0
    seen_numbers: Set[int] = set()
    heading_entry = entries[heading_index][1]
    heading_page = heading_entry.get("page") if isinstance(heading_entry, dict) else None

    def finalize_current() -> None:
        nonlocal current_number, current_parts, current_paragraphs
        if current_number and current_parts:
            text = " ".join(current_parts).strip()
            if text:
                paragraph_hashes = list(dict.fromkeys(current_paragraphs))
                items.append(
                    EnumeratedItem(
                        number=current_number,
                        text=text,
                        paragraph_hashes=paragraph_hashes,
                    )
                )
        current_number = None
        current_parts = []
        current_paragraphs = []

    for idx in range(heading_index + 1, len(entries)):
        hash_id, entry = entries[idx]
        text = (entry.get("text") or "").strip()

        if not text:
            if enumerating:
                blank_streak += 1
                if blank_streak >= 2:
                    break
            continue

        blank_streak = 0
        page = entry.get("page")
        if (
            isinstance(page, int)
            and isinstance(heading_page, int)
            and page - heading_page > 3
        ):
            finalize_current()
            break

        segments, prefix_text = _split_enumerated_segments(text)
        is_heading = _looks_like_section_heading(text)
        lower_text = text.lower()
        trimmed_text = text.strip()

        if segments:
            enumerating = True
            if prefix_text and current_number:
                current_parts.append(prefix_text.strip())
                current_paragraphs.append(hash_id)
            for number, segment in segments:
                try:
                    number_int = int(number)
                except (TypeError, ValueError):
                    continue
                if number_int > 50:
                    finalize_current()
                    return items
                if number_int in seen_numbers:
                    finalize_current()
                    continue
                finalize_current()
                current_number = number
                current_parts = [segment.strip()]
                current_paragraphs = [hash_id]
                seen_numbers.add(number_int)
            continue

        if not enumerating:
            if is_heading:
                break
            continue

        if trimmed_text.startswith("(") or (
            len(trimmed_text) <= 6 and trimmed_text.replace(".", "").replace(",", "").isalpha()
        ):
            finalize_current()
            break

        if lower_text.startswith("remarks:"):
            if prefix_text and current_number:
                current_parts.append(prefix_text.strip())
                current_paragraphs.append(hash_id)
            if current_number:
                current_parts.append(text)
                current_paragraphs.append(hash_id)
            continue

        if is_heading:
            finalize_current()
            break

        if current_number:
            current_parts.append(text)
            current_paragraphs.append(hash_id)

    finalize_current()
    try:
        items.sort(key=lambda item: int(item.number))
    except Exception:
        pass
    return items


def _split_enumerated_segments(text: str) -> Tuple[List[Tuple[str, str]], str]:
    matches = list(ITEM_SPLIT_PATTERN.finditer(text))
    if not matches:
        return [], ""
    prefix = text[: matches[0].start()]
    prefix_stripped = prefix.strip()
    allow_prefix = prefix_stripped.lower().startswith("remarks")
    if prefix_stripped and not allow_prefix:
        return [], ""
    segments: List[Tuple[str, str]] = []
    for idx, match in enumerate(matches):
        number = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        segment = text[start:end].strip()
        if segment:
            segments.append((number, segment))
    return segments, prefix


def _build_recommendation_from_item(
    document: ArticleDocument,
    item: EnumeratedItem,
    paragraph_store: Dict[str, Dict[str, object]],
) -> Optional[GuidelineRecommendation]:
    normalized_text = " ".join(item.text.split()).strip()
    if not normalized_text:
        return None

    try:
        normalized_label = str(int(item.number))
    except (TypeError, ValueError):
        normalized_label = item.number
    full_text = f"{normalized_label}. {normalized_text}"
    anchors = list(dict.fromkeys(item.paragraph_hashes))
    recommendation = GuidelineRecommendation(
        label=normalized_label,
        text=full_text,
        anchors=anchors.copy(),
        evidence_refs=anchors.copy(),
    )

    evidence_hash, entry = _select_evidence_hash(paragraph_store, anchors)
    if evidence_hash and entry:
        recommendation.evidence = _build_pointer(evidence_hash, entry)

    return recommendation


def _looks_like_section_heading(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    for pattern in SUMMARY_HEADING_PATTERNS:
        if pattern.match(stripped):
            return False
    if stripped.isupper() and any(char.isalpha() for char in stripped) and len(stripped) <= 120:
        return True
    if stripped.endswith(":") and len(stripped.split()) <= 8:
        return True
    return False


def _select_evidence_hash(
    paragraph_store: Dict[str, Dict[str, object]],
    hashes: Sequence[str],
) -> Tuple[Optional[str], Optional[Dict[str, object]]]:
    for hash_id in hashes:
        entry = paragraph_store.get(hash_id)
        if isinstance(entry, dict) and not entry.get("truncated"):
            return hash_id, entry
    for hash_id in hashes:
        entry = paragraph_store.get(hash_id)
        if isinstance(entry, dict):
            return hash_id, entry
    return None, None


def _stable_text_signature(text: str) -> str:
    normalized = " ".join(text.split()).strip().lower()
    digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=8)
    return digest.hexdigest()


def _grade_payload_from_raw(
    raw: Optional[str],
    *,
    scale_hint: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    if not raw:
        return None
    fragments = [segment.strip() for segment in str(raw).split(";") if segment and segment.strip()]
    for fragment in fragments:
        match = GRADE_CODE_INLINE_RE.search(fragment)
        if match:
            payload = map_grade_code(
                match.group(1),
                match.group(2),
                source="inline",
                confidence=0.82,
                raw=fragment,
                scale_hint=scale_hint,
            )
            if payload:
                return payload
        candidates = detect_inline_candidates(fragment) or detect_context_candidates(fragment)
        for candidate in candidates:
            payload = dict(candidate.to_payload())
            payload.setdefault("source", "inline")
            payload["raw"] = payload.get("raw") or fragment
            canonical_scale = canonicalize_scale(payload.get("scale"), raw=fragment, hint=scale_hint)
            if canonical_scale:
                payload["scale"] = canonical_scale
            elif payload.get("scale"):
                payload["scale"] = str(payload["scale"]).upper()
            return payload
    return None


def _finalize_recommendation_flags(rec: GuidelineRecommendation) -> None:
    normalized = getattr(rec, "grade_normalized", None) or {}
    graded_flag = bool(normalized) and not normalized.get("ungraded", False)
    typed_flag = False
    if normalized:
        typed_flag = True
    if not typed_flag:
        if _looks_like_recommendation_phrase(rec.text):
            typed_flag = True
        elif isinstance(rec.recommendation_type, str) and rec.recommendation_type in {"recommendation", "suggestion"}:
            typed_flag = True
    if not typed_flag and rec.label:
        typed_flag = True
    if not typed_flag and isinstance(rec.recommendation_type, str) and rec.recommendation_type == "consensus_statement":
        typed_flag = True

    rec.graded = graded_flag
    rec.typed = bool(typed_flag)

    if graded_flag:
        rec.ungraded = False
        rec.ungraded_reason = None
        if rec.statement_type != "consensus":
            rec.statement_type = "graded"
    elif normalized.get("ungraded", False):
        rec.ungraded = True
        if rec.statement_type != "consensus":
            rec.statement_type = "ungraded"
    elif rec.typed:
        rec.ungraded = True
        rec.ungraded_reason = rec.ungraded_reason or "grade_not_provided"
        if rec.statement_type not in {"consensus", "ungraded"}:
            rec.statement_type = "ungraded"
    else:
        rec.ungraded = bool(rec.ungraded)
        if rec.ungraded and rec.statement_type != "consensus":
            rec.statement_type = "ungraded"


def _recommendation_density_stats(
    recommendations: Sequence[GuidelineRecommendation],
) -> Tuple[int, int, float, float]:
    total = len(recommendations)
    if total == 0:
        return 0, 0, 0.0, 0.0
    with_grade = 0
    graded = 0
    typed_ungraded = 0
    for rec in recommendations:
        normalized = getattr(rec, "grade_normalized", None) or {}
        graded_flag = bool(getattr(rec, "graded", False))
        typed_flag = bool(getattr(rec, "typed", False) or normalized)
        if normalized:
            with_grade += 1
        if graded_flag:
            graded += 1
        elif typed_flag:
            typed_ungraded += 1
    typed_ungraded = min(typed_ungraded, max(0, total - graded))
    grade_density = with_grade / total if total else 0.0
    typed_density = (graded + typed_ungraded) / total if total else 0.0
    return graded, typed_ungraded, grade_density, typed_density


def _update_recommendation_metrics(document: ArticleDocument) -> None:
    recommendations = list(document.recommendations or [])
    for rec in recommendations:
        if getattr(rec, "ungraded", None) is None:
            rec.ungraded = False

    graded_count, typed_ungraded_count, grade_density, typed_density = _recommendation_density_stats(recommendations)

    pipeline_info = getattr(document, "pipeline_info", {})
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    metrics = pipeline_info.setdefault("recommendation_metrics", {})
    metrics.update(
        {
            "total": len(recommendations),
            "graded": graded_count,
            "typed_ungraded": typed_ungraded_count,
            "grade_density": round(grade_density, 4),
            "typed_density": round(typed_density, 4),
        }
    )
    grade_sources = pipeline_info.get("grade_source_breakdown") or metrics.get("grade_source_breakdown")
    if isinstance(grade_sources, dict):
        metrics["grade_source_breakdown"] = dict(grade_sources)
        pipeline_info["grade_source_breakdown"] = dict(grade_sources)
    pipeline_info["recommendations_count"] = len(recommendations)
    pipeline_info["graded_count"] = graded_count
    pipeline_info["typed_ungraded_count"] = typed_ungraded_count
    pipeline_info["grade_density"] = round(grade_density, 4)
    pipeline_info["typed_density"] = round(typed_density, 4)
    document.pipeline_info = pipeline_info


def _grade_density(recommendations: List[GuidelineRecommendation]) -> float:
    if not recommendations:
        return 0.0
    counted = sum(1 for rec in recommendations if getattr(rec, "grade_normalized", None))
    return counted / len(recommendations)


__all__ = ["enrich_guideline_document"]
