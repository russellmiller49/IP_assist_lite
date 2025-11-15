"""Second-pass patcher that lifts intended/indications content from Important Information chapters."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_intended_use_backfill"
WINDOW_MAX_CHARS_DEFAULT = 2400
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
DOT_LEADER_RE = re.compile(r"[.·…]{2,}\s*\d+$")
FALLBACK_KEYWORDS = (
    "intended use",
    "intended to",
    "indications",
    "purpose",
    "patient population",
)
BULLET_PREFIX_RE = re.compile(r"^[\u2022\u2023\u25E6\u25AA\u25CF■▪●•]+\s*")
GLOBAL_FALLBACK_TERMS = (
    "this equipment is intended",
    "this instrument is intended",
    "this device is intended",
)


def _ordered_entries(paragraph_store: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    ordered: List[Tuple[int, int, Dict[str, object]]] = []
    for hash_id, entry in paragraph_store.items():
        page = entry.get("page")
        page_index = page if isinstance(page, int) else 10**6
        orders = entry.get("order") or []
        order_index = 10**6
        if isinstance(orders, (list, tuple)):
            for raw in orders:
                try:
                    candidate = int(raw)
                except (TypeError, ValueError):
                    continue
                order_index = min(order_index, candidate)
        ordered.append((page_index, order_index, {**entry, "hash": hash_id}))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in ordered]


def _normalize_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned = [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
    return cleaned


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


def _slice_important_section(
    entries: List[Dict[str, object]],
    markers: List[str],
    window: int = 40,
    *,
    stop_patterns: Sequence[re.Pattern[str]] | None = None,
    max_chars: int = 0,
) -> List[Dict[str, object]]:
    if not markers:
        return []
    markers_lower = [marker.lower() for marker in markers]
    for idx, entry in enumerate(entries):
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        if _looks_like_toc(text):
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in markers_lower):
            end = min(len(entries), idx + window)
            subset = entries[idx:end]
            return _truncate_entries(
                subset,
                max_chars=max_chars,
                stop_patterns=stop_patterns,
            )
    return []


def _truncate_entries(
    entries: List[Dict[str, object]],
    *,
    max_chars: int,
    stop_patterns: Sequence[re.Pattern[str]] | None,
) -> List[Dict[str, object]]:
    if not entries:
        return []
    limited: List[Dict[str, object]] = []
    total_chars = 0
    for entry in entries:
        text = entry.get("text")
        if not isinstance(text, str):
            limited.append(entry)
            continue
        if _looks_like_toc(text):
            continue
        lines = text.splitlines()
        kept_lines: List[str] = []
        stop_hit = False
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if stop_patterns and any(pattern.search(lowered) for pattern in stop_patterns):
                stop_hit = True
                break
            kept_lines.append(raw_line)
            total_chars += len(raw_line)
            if max_chars and total_chars >= max_chars:
                stop_hit = True
                break
        if kept_lines:
            limited.append({**entry, "text": "\n".join(kept_lines)})
        if stop_hit:
            break
        if max_chars and total_chars >= max_chars:
            break
    return limited or entries


def _looks_like_toc(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    if DOT_LEADER_RE.search(cleaned):
        return True
    if re.search(r"\s\d+$", cleaned) and len(cleaned.split()) <= 12:
        return True
    return False


def _first_meaningful_sentence(entries: List[Dict[str, object]]) -> Optional[str]:
    candidates: List[str] = []
    for entry in entries:
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        if _looks_like_toc(text):
            continue
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped:
                lowered = stripped.lower()
                if any(keyword in lowered for keyword in FALLBACK_KEYWORDS):
                    return stripped
                candidates.append(stripped)
    return candidates[0] if candidates else None


def _strip_bullet_prefix(text: str) -> str:
    return BULLET_PREFIX_RE.sub("", text or "").strip()


def _find_global_fallback_sentence(
    entries: List[Dict[str, object]],
) -> Tuple[Optional[str], Optional[str]]:
    for entry in entries:
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if any(keyword in lowered for keyword in GLOBAL_FALLBACK_TERMS):
                return stripped, entry.get("hash")
    return None, None


def _find_following_sentence(
    entries: List[Dict[str, object]],
    start_idx: int,
    window: int = 10,
    stop_set: Optional[set[str]] = None,
) -> Optional[str]:
    end = min(len(entries), start_idx + window + 1)
    for idx in range(start_idx + 1, end):
        entry = entries[idx]
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if stop_set and lowered in stop_set:
                continue
            if any(keyword in lowered for keyword in GLOBAL_FALLBACK_TERMS):
                return stripped
    return None


def _next_non_empty_line(
    entries: List[Dict[str, object]],
    entry_idx: int,
    line_idx: int,
    local_lines: List[str],
) -> Optional[str]:
    for idx in range(line_idx + 1, len(local_lines)):
        candidate = local_lines[idx].strip()
        if candidate:
            return candidate
    for offset in range(1, 4):
        target_idx = entry_idx + offset
        if target_idx >= len(entries):
            break
        text = entries[target_idx].get("text")
        if not isinstance(text, str):
            continue
        for raw_line in text.splitlines():
            candidate = raw_line.strip()
            if candidate:
                return candidate
    return None


def _find_anchor_sentence(
    entries: List[Dict[str, object]],
    anchors: List[str],
    allowed_hashes: Optional[set[str]] = None,
    stop_labels: Optional[Sequence[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    if not anchors:
        return None, None
    anchors_lower = [anchor.lower() for anchor in anchors]
    stop_set = {label.strip().lower() for label in stop_labels or [] if label}
    for entry_idx, entry in enumerate(entries):
        entry_hash = entry.get("hash")
        if allowed_hashes is not None and entry_hash not in allowed_hashes:
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            continue
        for line_idx, raw_line in enumerate(lines):
            stripped = _strip_bullet_prefix(raw_line.strip())
            lowered = stripped.lower()
            for anchor_lower in anchors_lower:
                if lowered.startswith(anchor_lower):
                    remainder = stripped[len(anchor_lower):].lstrip(" ：:-–—")
                    if remainder:
                        return remainder, _hash_for_entry(entry)
                    fallback = _next_non_empty_line(entries, entry_idx, line_idx, lines)
                    if fallback:
                        cleaned_fallback = _strip_bullet_prefix(fallback.strip())
                        if cleaned_fallback and cleaned_fallback.lower() not in stop_set:
                            return cleaned_fallback, _hash_for_entry(entry)
                    follow_up = _find_following_sentence(entries, entry_idx, window=20, stop_set=stop_set)
                    if follow_up:
                        return follow_up, _hash_for_entry(entry)
                elif lowered == anchor_lower:
                    fallback = _next_non_empty_line(entries, entry_idx, line_idx, lines)
                    if fallback:
                        cleaned_fallback = _strip_bullet_prefix(fallback.strip())
                        if cleaned_fallback and cleaned_fallback.lower() not in stop_set:
                            return cleaned_fallback, _hash_for_entry(entry)
                    follow_up = _find_following_sentence(entries, entry_idx, window=20, stop_set=stop_set)
                    if follow_up:
                        return follow_up, _hash_for_entry(entry)
    return None, None


def _hash_for_entry(entry: Dict[str, object]) -> Optional[str]:
    hash_id = entry.get("hash")
    if hash_id is None:
        return None
    return str(hash_id)


def _page_range_for_hash(hash_id: Optional[str], store: Dict[str, Dict[str, object]]) -> List[int]:
    if not hash_id or not store:
        return []
    entry = store.get(hash_id)
    if not isinstance(entry, dict):
        return []
    pages: List[int] = []
    page_value = entry.get("page")
    if isinstance(page_value, int):
        pages.append(page_value)
    pages_list = entry.get("pages")
    if isinstance(pages_list, list):
        for candidate in pages_list:
            try:
                pages.append(int(candidate))
            except (TypeError, ValueError):
                continue
    if not pages:
        return []
    return [min(pages), max(pages)]


def _fallback_contra_sentence(entries: List[Dict[str, object]]) -> Optional[str]:
    anchor_pending = False
    window = 0
    for entry in entries:
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lowered = text.lower()
        if "contraindications" in lowered:
            anchor_pending = True
            window = 2
            if "none" in lowered:
                return text.strip()
            continue
        if anchor_pending:
            window -= 1
            if "none" in lowered:
                return text.strip()
            if window <= 0:
                anchor_pending = False
    return None


def _trim_sentence(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = cleaned.rstrip(".;") + "."
    cleaned = cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
    if cleaned.lower() in {"none known.", "none."}:
        return "None known."
    return cleaned


def _trim_english(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = cleaned.rstrip(".;") + "."
    return cleaned


def _extract_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _is_placeholder(text: str) -> bool:
    stripped = text.strip().strip(".-")
    return not stripped


def apply_ifu_intended_use_backfill(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    existing_indications = _extract_text(document.indications_for_use)
    existing_intended = _extract_text(document.intended_use)
    needs_indications = not existing_indications or _is_placeholder(existing_indications)
    needs_intended = not existing_intended or _is_placeholder(existing_intended)
    needs_contra = not (document.contraindications or [])

    if not (needs_indications or needs_intended or needs_contra):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="fields_complete")

    anchors_cfg = {}
    if isinstance(ctx.config, dict):
        ifu_cfg = ctx.config.get("ifu", {})
        if isinstance(ifu_cfg, dict):
            anchors_cfg = ifu_cfg.get("anchors", {}) if isinstance(ifu_cfg.get("anchors"), dict) else {}

    stop_labels_raw = anchors_cfg.get("stop_headings", STOP_HEADING_DEFAULTS)
    if isinstance(stop_labels_raw, Sequence):
        stop_patterns = _compile_stop_patterns(stop_labels_raw)
        stop_label_set = {str(label).strip().lower() for label in stop_labels_raw if label}
    else:
        stop_patterns = _compile_stop_patterns(STOP_HEADING_DEFAULTS)
        stop_label_set = {label.lower() for label in STOP_HEADING_DEFAULTS}
    try:
        max_window_chars = int(anchors_cfg.get("window_max_chars", WINDOW_MAX_CHARS_DEFAULT) or WINDOW_MAX_CHARS_DEFAULT)
    except (TypeError, ValueError):
        max_window_chars = WINDOW_MAX_CHARS_DEFAULT

    important_terms = _normalize_list(anchors_cfg.get("important_info"))
    indication_terms = _normalize_list(anchors_cfg.get("indications_en"))
    contra_terms = _normalize_list(anchors_cfg.get("contraindications"))

    paragraph_store = ctx.paragraph_store or {}
    ordered_entries = _ordered_entries(paragraph_store)
    important_window = _slice_important_section(
        ordered_entries,
        important_terms,
        stop_patterns=stop_patterns,
        max_chars=max_window_chars,
    )
    if important_window:
        search_entries = important_window
    else:
        search_entries = _truncate_entries(
            ordered_entries,
            max_chars=max_window_chars,
            stop_patterns=stop_patterns,
        )
    if not search_entries:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="important_section_missing")

    allowed_hashes = {entry.get("hash") for entry in search_entries if entry.get("hash")}
    indication_sentence, indication_hash = _find_anchor_sentence(
        ordered_entries,
        indication_terms,
        allowed_hashes if allowed_hashes else None,
        stop_labels=stop_label_set,
    )
    if not indication_sentence and important_window:
        fallback_entries = _truncate_entries(
            ordered_entries,
            max_chars=max_window_chars,
            stop_patterns=stop_patterns,
        )
        if fallback_entries:
            search_entries = fallback_entries
            allowed_hashes = {entry.get("hash") for entry in search_entries if entry.get("hash")}
            indication_sentence, indication_hash = _find_anchor_sentence(
                ordered_entries,
                indication_terms,
                allowed_hashes if allowed_hashes else None,
                stop_labels=stop_label_set,
            )
    if not indication_sentence:
        fallback_sentence = _first_meaningful_sentence(search_entries)
        if fallback_sentence:
            indication_sentence = fallback_sentence
            indication_hash = search_entries[0].get("hash") if search_entries else None
    if not indication_sentence:
        global_sentence, global_hash = _find_global_fallback_sentence(ordered_entries)
        if global_sentence:
            indication_sentence = global_sentence
            indication_hash = global_hash

    contra_sentence_raw, _ = _find_anchor_sentence(
        ordered_entries,
        contra_terms,
        allowed_hashes if allowed_hashes else None,
        stop_labels=stop_label_set,
    )
    contra_sentence = contra_sentence_raw or _fallback_contra_sentence(ordered_entries)

    trimmed_indication = _trim_english(indication_sentence)
    trimmed_contra = _trim_sentence(contra_sentence)

    modifications: Dict[str, int] = {}

    if trimmed_indication and needs_intended:
        document.intended_use = trimmed_indication
        modifications["intended_use"] = modifications.get("intended_use", 0) + 1

    if trimmed_indication and needs_indications:
        payload: Dict[str, object] = {
            "text": trimmed_indication,
            "provenance": "second_pass_important_information",
            "derived_from": "important_information",
        }
        if indication_hash:
            payload["evidence_ids"] = [indication_hash]
            payload["evidence_refs"] = [indication_hash]
            payload["evidence_span"] = {
                "first": indication_hash,
                "last": indication_hash,
            }
            pages_span = _page_range_for_hash(indication_hash, paragraph_store)
            if pages_span:
                payload["page_range"] = pages_span
        document.indications_for_use = payload
        modifications["indications_for_use"] = modifications.get("indications_for_use", 0) + 1

    if trimmed_contra and needs_contra:
        document.contraindications = [trimmed_contra]
        modifications["contraindications"] = modifications.get("contraindications", 0) + 1

    if not modifications:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_anchor_match")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}

    pipeline_info["indications_fallback_provenance"] = "important_information"
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
    if "indications_from_important_information" not in reasons_list:
        reasons_list.append("indications_from_important_information")

    modifications_bucket = second_pass_bucket.setdefault("modifications", {})
    for key, value in modifications.items():
        modifications_bucket[key] = modifications_bucket.get(key, 0) + value

    meta = second_pass_bucket.setdefault("meta", {})
    for key, value in modifications.items():
        meta[key] = meta.get(key, 0) + value

    pipeline_info["second_pass"] = second_pass_bucket
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=dict(modifications),
        reasons=["indications_from_important_information"],
    )


__all__ = ["apply_ifu_intended_use_backfill"]
