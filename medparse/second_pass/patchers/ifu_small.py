"""Second-pass patcher for bilingual small IFU leaflets."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_small_leaflet_map"
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
CLEANING_PREFIXES = ("clean", "rinse", "perform", "immerse", "wipe", "wash", "dry")


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


def _next_non_empty_line(
    entries: List[Dict[str, object]],
    entry_idx: int,
    line_idx: int,
    local_lines: List[str],
) -> Optional[str]:
    # Same entry
    for idx in range(line_idx + 1, len(local_lines)):
        candidate = local_lines[idx].strip()
        if candidate:
            return candidate
    # Subsequent entries (limit to 2)
    for offset in range(1, 3):
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
) -> Tuple[Optional[str], Optional[int]]:
    if not anchors:
        return None, None
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
            for anchor_lower, anchor in zip(anchors_lower, anchors):
                if not stripped:
                    continue
                if lowered.startswith(anchor_lower):
                    remainder = stripped[len(anchor_lower):].lstrip(" ：:-–—")
                    if remainder:
                        return remainder, entry.get("page") if isinstance(entry.get("page"), int) else None
                    fallback = _next_non_empty_line(entries, entry_idx, line_idx, lines)
                    if fallback:
                        return fallback, entry.get("page") if isinstance(entry.get("page"), int) else None
                elif lowered == anchor_lower:
                    fallback = _next_non_empty_line(entries, entry_idx, line_idx, lines)
                    if fallback:
                        return fallback, entry.get("page") if isinstance(entry.get("page"), int) else None
    return None, None


def _looks_like_cleaning_step(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(lowered.startswith(prefix) for prefix in CLEANING_PREFIXES)


def _trim_english_sentence(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"^(?:intended\s+use|indications?\s+for\s+use)[:：\-–—\s]*", "", text.strip(), flags=re.IGNORECASE)
    if not cleaned:
        return None
    sentences = SENTENCE_SPLIT_RE.split(cleaned)
    if not sentences:
        sentences = [cleaned]
    for sentence in sentences:
        candidate = sentence.strip()
        if not candidate:
            continue
        if _looks_like_cleaning_step(candidate):
            continue
        return candidate
    return cleaned.strip()


def _trim_japanese_sentence(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"^使用目的[:：\s]*", "", text.strip())
    parts = [part for part in cleaned.split("。") if part.strip()]
    if not parts:
        return cleaned.strip() or None
    first = parts[0].strip()
    return f"{first}。"


def _extract_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _ensure_second_pass_bucket(pipeline_info: Dict[str, object]) -> Dict[str, object]:
    bucket = pipeline_info.setdefault("second_pass", {})
    if not isinstance(bucket, dict):
        bucket = {}
        pipeline_info["second_pass"] = bucket
    return bucket


def _store_localized_metadata(pipeline_info: Dict[str, object], jap_text: str) -> None:
    localized = pipeline_info.setdefault("localized", {})
    if not isinstance(localized, dict):
        localized = {}
        pipeline_info["localized"] = localized
    indications_block = localized.setdefault("indications", {})
    if not isinstance(indications_block, dict):
        indications_block = {}
        localized["indications"] = indications_block
    indications_block["ja"] = jap_text


def apply_ifu_small_leaflet_map(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    page_threshold = 4
    if isinstance(ctx.config, dict):
        density_cfg = ctx.config.get("ifu", {}).get("safety_density_min", {})
        if isinstance(density_cfg, dict):
            try:
                page_threshold = int(density_cfg.get("small_leaflet_pages_max", page_threshold))
            except (TypeError, ValueError):
                page_threshold = 4
    if (document.page_count or 0) > page_threshold:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="page_count_too_high")

    paragraph_store = ctx.paragraph_store or {}
    ordered_entries = _ordered_entries(paragraph_store)

    anchors_cfg = {}
    if isinstance(ctx.config, dict):
        ifu_cfg = ctx.config.get("ifu", {})
        if isinstance(ifu_cfg, dict):
            anchors_cfg = ifu_cfg.get("anchors", {}) if isinstance(ifu_cfg.get("anchors"), dict) else {}
    en_terms = _normalize_list(anchors_cfg.get("indications_en"))
    ja_terms = _normalize_list(anchors_cfg.get("indications_ja"))

    english_anchor_text, anchor_page = _find_anchor_sentence(ordered_entries, en_terms)
    english_trimmed = _trim_english_sentence(english_anchor_text)

    existing_intended = _extract_text(document.intended_use)
    if not english_trimmed and existing_intended:
        english_trimmed = _trim_english_sentence(existing_intended)

    existing_indications = _extract_text(document.indications_for_use)
    if not english_trimmed and existing_indications:
        english_trimmed = _trim_english_sentence(existing_indications)

    if not english_trimmed:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_purpose_sentence")

    japanese_anchor_text, _ = _find_anchor_sentence(ordered_entries, ja_terms)
    japanese_trimmed = _trim_japanese_sentence(japanese_anchor_text)

    intent_modified = False
    if document.intended_use != english_trimmed:
        document.intended_use = english_trimmed
        intent_modified = True

    indications_payload = {
        "text": english_trimmed,
        "provenance": "second_pass_small_leaflet",
        "derived_from": "intended_use",
    }

    indications_modified = False
    if existing_indications != english_trimmed or not isinstance(document.indications_for_use, dict):
        document.indications_for_use = indications_payload
        indications_modified = True

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}

    if japanese_trimmed:
        _store_localized_metadata(pipeline_info, japanese_trimmed)
    if anchor_page is not None:
        pipeline_info["indications_anchor_page"] = anchor_page

    if not intent_modified and not indications_modified and not japanese_trimmed:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_change")

    pipeline_info["indications_fallback_provenance"] = "second_pass_small_leaflet"
    second_pass_bucket = _ensure_second_pass_bucket(pipeline_info)

    patches_applied = second_pass_bucket.setdefault("patches_applied", [])
    if PATCH_NAME not in patches_applied:
        patches_applied.append(PATCH_NAME)

    applied_list = second_pass_bucket.setdefault("applied", [])
    if PATCH_NAME not in applied_list:
        applied_list.append(PATCH_NAME)

    reasons_list = second_pass_bucket.setdefault("reasons", [])
    if "small_leaflet_mapper" not in reasons_list:
        reasons_list.append("small_leaflet_mapper")

    modifications_bucket = second_pass_bucket.setdefault("modifications", {})
    meta = second_pass_bucket.setdefault("meta", {})
    mod_payload: Dict[str, int] = {}
    if indications_modified:
        modifications_bucket["indications_for_use"] = modifications_bucket.get("indications_for_use", 0) + 1
        meta["indications_for_use"] = meta.get("indications_for_use", 0) + 1
        mod_payload["indications_for_use"] = 1
    if intent_modified:
        modifications_bucket["intended_use"] = modifications_bucket.get("intended_use", 0) + 1
        meta["intended_use"] = meta.get("intended_use", 0) + 1
        mod_payload["intended_use"] = 1
    if japanese_trimmed and not mod_payload:
        mod_payload["localized_indications"] = 1

    pipeline_info["second_pass"] = second_pass_bucket
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=mod_payload or {"localized_indications": 1},
        reasons=["small_leaflet_mapper"],
    )


__all__ = ["apply_ifu_small_leaflet_map"]
