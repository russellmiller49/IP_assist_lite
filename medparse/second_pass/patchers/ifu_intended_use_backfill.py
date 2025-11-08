"""Second-pass patcher that lifts intended/indications content from Important Information chapters."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_intended_use_backfill"


def _ordered_entries(paragraph_store: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    ordered: List[Tuple[int, int, Dict[str, object]]] = []
    for entry in paragraph_store.values():
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
        ordered.append((page_index, order_index, entry))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in ordered]


def _normalize_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned = [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
    return cleaned


def _slice_important_section(entries: List[Dict[str, object]], markers: List[str], window: int = 40) -> List[Dict[str, object]]:
    if not markers:
        return []
    markers_lower = [marker.lower() for marker in markers]
    for idx, entry in enumerate(entries):
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in markers_lower):
            end = min(len(entries), idx + window)
            return entries[idx:end]
    return []


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
) -> Optional[str]:
    if not anchors:
        return None
    anchors_lower = [anchor.lower() for anchor in anchors]
    for entry_idx, entry in enumerate(entries):
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            continue
        for line_idx, raw_line in enumerate(lines):
            stripped = raw_line.strip()
            lowered = stripped.lower()
            for anchor_lower in anchors_lower:
                if lowered.startswith(anchor_lower):
                    remainder = stripped[len(anchor_lower):].lstrip(" ：:-–—")
                    if remainder:
                        return remainder
                    fallback = _next_non_empty_line(entries, entry_idx, line_idx, lines)
                    if fallback:
                        return fallback
                elif lowered == anchor_lower:
                    fallback = _next_non_empty_line(entries, entry_idx, line_idx, lines)
                    if fallback:
                        return fallback
    return None


def _fallback_contra_sentence(entries: List[Dict[str, object]]) -> Optional[str]:
    for entry in entries:
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lowered = text.lower()
        if "contraindications" in lowered and "none" in lowered:
            return "None known."
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

    important_terms = _normalize_list(anchors_cfg.get("important_info"))
    indication_terms = _normalize_list(anchors_cfg.get("indications_en"))
    contra_terms = _normalize_list(anchors_cfg.get("contraindications"))

    ordered_entries = _ordered_entries(ctx.paragraph_store or {})
    important_window = _slice_important_section(ordered_entries, important_terms)
    search_entries = important_window or ordered_entries
    if not search_entries:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="important_section_missing")

    indication_sentence = _find_anchor_sentence(search_entries, indication_terms)
    contra_sentence = _find_anchor_sentence(search_entries, contra_terms) or _fallback_contra_sentence(ordered_entries)

    trimmed_indication = _trim_english(indication_sentence)
    trimmed_contra = _trim_sentence(contra_sentence)

    modifications: Dict[str, int] = {}

    if trimmed_indication and needs_intended:
        document.intended_use = trimmed_indication
        modifications["intended_use"] = modifications.get("intended_use", 0) + 1

    if trimmed_indication and needs_indications:
        document.indications_for_use = {
            "text": trimmed_indication,
            "provenance": "second_pass_important_information",
            "derived_from": "important_information",
        }
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
