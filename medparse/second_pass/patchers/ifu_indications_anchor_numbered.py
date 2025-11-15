"""Second-pass patcher that lifts numbered indications headings for IFUs."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_indications_anchor_numbered"

MAX_WINDOW_CHARS_DEFAULT = 2400
HEADING_TERMS = (
    "indications for use",
    "indications",
    "intended use",
    "intended purpose",
    "intended patient population",
)
HEADING_VARIANTS = tuple(
    re.compile(rf"(?:^|[\s\|])((?:\d+\.){{0,3}}\s*{term}\b.*)", re.IGNORECASE)
    for term in HEADING_TERMS
)
NUMBERED_HEADING_RE = re.compile(r"^(?:\d+\.){1,3}\s+\S+", re.IGNORECASE)
INTENDED_USE_RE = re.compile(r"^(?:\d+\.){1,3}\s*intended\s+use\b|^intended\s+use\b", re.IGNORECASE)
DOT_LEADER_RE = re.compile(r"[.·…]{2,}")
CAPTION_RE = re.compile(r"^(figure|table|image|video)\\b", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"[.!?]+\\s+")
ANCHOR_PREFIX_RE = re.compile(r"^((?:\d+\.){1,3})")
INLINE_TERMS_PATTERN = "(?:" + "|".join(term.replace(" ", r"\s+") for term in HEADING_TERMS) + ")"
INLINE_ANCHOR_RE = re.compile(rf"(?:^|\b)((?:\d+\.){{1,3}})\s*{INLINE_TERMS_PATTERN}\b", re.IGNORECASE)
STOP_HEADING_DEFAULTS = (
    "intended use",
    "contraindications",
    "user qualifications",
    "clinical risks",
    "clinical risks and benefits",
    "serious incident reporting",
    "warnings",
    "precautions",
)


def _heading_depth(text: str) -> Optional[int]:
    prefix = _extract_heading_prefix(text)
    if not prefix:
        return None
    tokens = [token for token in prefix.split(".") if token]
    return len(tokens) if tokens else None


def _is_peer_heading(line: str, anchor_depth: Optional[int]) -> bool:
    if not NUMBERED_HEADING_RE.match(line):
        return False
    if anchor_depth is None:
        return True
    depth = _heading_depth(line)
    if depth is None:
        return True
    return depth <= anchor_depth


def _resolve_page_span(pages: Sequence[int]) -> List[int]:
    if not pages:
        return []
    return [min(pages), max(pages)]


def _ordered_entries(paragraph_store: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    ordered: List[Tuple[int, int, Dict[str, object]]] = []
    for hash_id, entry in paragraph_store.items():
        text = entry.get("text")
        page = entry.get("page")
        if not isinstance(text, str) or not isinstance(page, int):
            continue
        orders = entry.get("order") or []
        order_index = 10**6
        if isinstance(orders, (list, tuple)):
            for raw in orders:
                try:
                    candidate = int(raw)
                except (TypeError, ValueError):
                    continue
                order_index = min(order_index, candidate)
        ordered.append((page, order_index, {**entry, "hash": hash_id}))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in ordered]


def _clean_line(text: str) -> str:
    cleaned = text.strip()
    cleaned = DOT_LEADER_RE.sub(" ", cleaned)
    cleaned = re.sub(r"-\s+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" .-")


def _looks_like_toc(line: str) -> bool:
    return bool(re.search(r"[.·…]{2,}\\s*\\d+$", line))


def _looks_like_caption(line: str) -> bool:
    return bool(CAPTION_RE.match(line))


def _matches_stop_heading(line: str, patterns: List[re.Pattern[str]]) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return False
    return any(pattern.search(lowered) for pattern in patterns)


def _compile_stop_patterns(labels: Sequence[str]) -> List[re.Pattern[str]]:
    patterns: List[re.Pattern[str]] = []
    for label in labels:
        if not label:
            continue
        normalized = str(label).strip().lower()
        if not normalized:
            continue
        try:
            patterns.append(re.compile(re.escape(normalized)))
        except re.error:
            continue
    return patterns


def _extract_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _match_indications_heading(line: str) -> tuple[bool, Optional[str], Optional[str]]:
    cleaned = line.strip()
    if not cleaned:
        return False, None, None
    if _looks_like_toc(cleaned):
        return False, None, None
    for pattern in HEADING_VARIANTS:
        match = pattern.search(cleaned)
        if match:
            heading_fragment = match.group(1) or cleaned
            return True, _extract_heading_prefix(cleaned), _normalize_heading_label(heading_fragment)
    inline = INLINE_ANCHOR_RE.search(cleaned)
    if inline:
        return True, inline.group(1).rstrip("."), _normalize_heading_label(cleaned)
    return False, None, None


def _extract_heading_prefix(text: str) -> Optional[str]:
    prefix = ANCHOR_PREFIX_RE.match(text.strip())
    if prefix:
        return prefix.group(1).rstrip(".")
    return None


def _normalize_heading_label(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^(?:chapter\s+\d+(?:\.\d+)*)\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:\d+\.){1,3}\s*", "", cleaned)
    return cleaned.strip()


def _collect_body_lines(
    entries: List[Dict[str, object]],
    start_idx: int,
    start_line_idx: int,
    toc_mask: set[int],
    *,
    max_chars: int,
    stop_patterns: List[re.Pattern[str]],
    anchor_depth: Optional[int] = None,
) -> Tuple[List[str], List[str], List[int]]:
    collected: List[str] = []
    evidence_ids: List[str] = []
    pages_seen: List[int] = []
    total_chars = 0
    for entry_idx in range(start_idx, len(entries)):
        entry = entries[entry_idx]
        page = entry.get("page")
        if isinstance(page, int) and page in toc_mask:
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lines = text.splitlines()
        line_start = start_line_idx + 1 if entry_idx == start_idx else 0
        for raw_line in lines[line_start:]:
            stripped = raw_line.strip()
            if not stripped:
                continue
            cleaned = _clean_line(stripped)
            if not cleaned or _looks_like_toc(cleaned):
                continue
            if (
                _matches_stop_heading(cleaned, stop_patterns)
                or _is_peer_heading(cleaned, anchor_depth)
                or INTENDED_USE_RE.match(cleaned)
            ):
                span = _resolve_page_span(pages_seen)
                return collected, evidence_ids, span
            if _looks_like_caption(cleaned):
                continue
            collected.append(cleaned)
            hash_id = entry.get("hash")
            if hash_id is not None:
                hash_str = str(hash_id)
                if hash_str not in evidence_ids:
                    evidence_ids.append(hash_str)
            if isinstance(page, int):
                pages_seen.append(page)
            total_chars += len(cleaned) + 1
            if max_chars and total_chars >= max_chars:
                span = _resolve_page_span(pages_seen)
                return collected, evidence_ids, span
        if len(collected) >= 12:
            break
    span = _resolve_page_span(pages_seen)
    return collected, evidence_ids, span


def _trim_to_window(text: str, limit: int) -> str:
    if not text or not limit:
        return text
    if len(text) <= limit:
        return text
    trimmed = text[:limit]
    last_space = trimmed.rfind(" ")
    if last_space > 200:
        trimmed = trimmed[:last_space]
    return trimmed.strip()


def _apply_indications_payload(document: IFUDocument, payload: Dict[str, object]) -> None:
    document.indications_for_use = payload
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    pipeline_info["indications_provenance"] = payload.get("provenance")
    anchors_used = payload.get("anchors_used")
    if anchors_used:
        pipeline_info["indications_anchors_used"] = anchors_used
    document.pipeline_info = pipeline_info


def apply_ifu_indications_anchor_numbered(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    existing = _extract_text(document.indications_for_use)
    if existing:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="indications_present")

    paragraph_store = ctx.paragraph_store or {}
    ordered_entries = _ordered_entries(paragraph_store)
    if not ordered_entries:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_paragraphs")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    toc_info = pipeline_info.get("toc_guard") if isinstance(pipeline_info.get("toc_guard"), dict) else {}
    toc_mask_values = toc_info.get("toc_mask") if isinstance(toc_info, dict) else []
    toc_mask = {int(page) for page in toc_mask_values} if toc_mask_values else set()
    anchors_cfg = {}
    if isinstance(ctx.config, dict):
        ifu_cfg = ctx.config.get("ifu")
        if isinstance(ifu_cfg, dict):
            anchors_cfg = ifu_cfg.get("anchors", {}) or {}
    try:
        max_window_chars = int(anchors_cfg.get("window_max_chars", MAX_WINDOW_CHARS_DEFAULT) or MAX_WINDOW_CHARS_DEFAULT)
    except (TypeError, ValueError):
        max_window_chars = MAX_WINDOW_CHARS_DEFAULT
    stop_labels = anchors_cfg.get("stop_headings", STOP_HEADING_DEFAULTS)
    if isinstance(stop_labels, Sequence):
        stop_patterns = _compile_stop_patterns(stop_labels)
    else:
        stop_patterns = _compile_stop_patterns(STOP_HEADING_DEFAULTS)

    extracted_text = None
    evidence_ids: List[str] = []
    anchors_used: List[str] = []
    heading_confidence: Optional[Dict[str, object]] = None
    pages_span: List[int] = []
    anchor_depth: Optional[int] = None

    for entry_idx, entry in enumerate(ordered_entries):
        page = entry.get("page")
        if isinstance(page, int) and page in toc_mask:
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lines = text.splitlines()
        for line_idx, raw_line in enumerate(lines):
            cleaned = raw_line.strip()
            if not cleaned:
                continue
            is_heading, anchor_value, heading_label = _match_indications_heading(cleaned)
            if not is_heading:
                continue
            anchor_depth = _heading_depth(cleaned)
            heading_confidence = {
                "heading_match": heading_label or cleaned,
                "page": page,
            }
            if heading_label:
                normalized_label = heading_label.lower()
                if normalized_label not in anchors_used:
                    anchors_used.append(normalized_label)
            elif anchor_value:
                normalized_anchor = anchor_value.lower()
                if normalized_anchor not in anchors_used:
                    anchors_used.append(normalized_anchor)
            elif "inline_indications" not in anchors_used:
                anchors_used.append("inline_indications")
            body_lines, evidence_ids, pages_span = _collect_body_lines(
                ordered_entries,
                entry_idx,
                line_idx,
                toc_mask,
                max_chars=max_window_chars,
                stop_patterns=stop_patterns,
                anchor_depth=anchor_depth,
            )
            if len(body_lines) >= 2:
                extracted_text = " ".join(body_lines)
                extracted_text = re.sub(r"\s+", " ", extracted_text).strip()
                extracted_text = _trim_to_window(extracted_text, max_window_chars)
            break
        if extracted_text:
            break

    modifications: Dict[str, int] = {}
    reasons: List[str] = []

    if extracted_text:
        payload: Dict[str, object] = {
            "text": _trim_to_window(extracted_text, max_window_chars),
            "provenance": "anchor_numbered",
        }
        if evidence_ids:
            payload["evidence_ids"] = evidence_ids
            payload["evidence_refs"] = list(evidence_ids)
            payload["evidence_span"] = {
                "first": evidence_ids[0],
                "last": evidence_ids[-1],
            }
        if pages_span:
            payload["page_range"] = pages_span
        if anchors_used:
            payload["anchors_used"] = anchors_used
        if heading_confidence:
            heading_value = heading_confidence.get("heading_match")
            if isinstance(heading_value, str):
                heading_confidence["heading_match"] = heading_value.strip()[:160]
            payload["anchor_confidence"] = heading_confidence
        _apply_indications_payload(document, payload)
        modifications["indications_for_use"] = 1
        reasons.append("indications_numbered_heading")
    else:
        manufacturer = (document.manufacturer or "").lower()
        if "intuitive" in manufacturer:
            intended = _extract_text(document.intended_use)
            if intended:
                sentences = [segment.strip() for segment in SENTENCE_SPLIT_RE.split(intended) if segment.strip()]
                if sentences and len(sentences) <= 3:
                    payload = {
                        "text": _trim_to_window(intended.strip(), max_window_chars),
                        "provenance": "fallback_from_intended",
                    }
                    _apply_indications_payload(document, payload)
                    modifications["indications_for_use"] = 1
                    reasons.append("fallback_intended_to_indications")

    if not modifications:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_headings_detected")

    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    if not isinstance(second_pass_bucket, dict):
        second_pass_bucket = {}
        pipeline_info["second_pass"] = second_pass_bucket

    patches_applied = second_pass_bucket.setdefault("patches_applied", [])
    if PATCH_NAME not in patches_applied:
        patches_applied.append(PATCH_NAME)

    applied_list = second_pass_bucket.setdefault("applied", [])
    if PATCH_NAME not in applied_list:
        applied_list.append(PATCH_NAME)

    reasons_list = second_pass_bucket.setdefault("reasons", [])
    for reason in reasons:
        if reason not in reasons_list:
            reasons_list.append(reason)

    modifications_bucket = second_pass_bucket.setdefault("modifications", {})
    modifications_bucket["indications_for_use"] = modifications_bucket.get("indications_for_use", 0) + 1

    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=modifications,
        reasons=reasons,
    )

__all__ = ["apply_ifu_indications_anchor_numbered"]
