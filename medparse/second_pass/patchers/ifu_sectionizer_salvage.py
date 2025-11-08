"""Second-pass sectionizer salvage for IFU documents."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_sectionizer_salvage"

CHAPTER_PATTERN = re.compile(r"^chapter\s+\d+[A-Za-z0-9 .-]*", re.IGNORECASE)
NUMERIC_PATTERN = re.compile(r"^\d+(?:\.\d+)*\s+[A-Za-z].{2,}")


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


def _detect_headings(entries: List[Dict[str, object]], anchors: List[str]) -> List[Tuple[str, int]]:
    detected: List[Tuple[str, int]] = []
    anchor_lower = [anchor.lower() for anchor in anchors]
    for entry in entries:
        text = entry.get("text")
        page = entry.get("page")
        if not isinstance(text, str) or not isinstance(page, int):
            continue
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if CHAPTER_PATTERN.match(stripped) or NUMERIC_PATTERN.match(stripped):
                detected.append((stripped, page))
                continue
            if any(stripped.lower().startswith(anchor) for anchor in anchor_lower):
                detected.append((stripped, page))
    return detected


def apply_ifu_sectionizer_salvage(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    sections = getattr(document, "sections", None)
    has_sections = isinstance(sections, dict) and sections
    if has_sections and len(sections) >= 3:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="sections_present")

    anchors_cfg = {}
    if isinstance(ctx.config, dict):
        ifu_cfg = ctx.config.get("ifu", {})
        if isinstance(ifu_cfg, dict):
            anchors_cfg = ifu_cfg.get("anchors", {}) if isinstance(ifu_cfg.get("anchors"), dict) else {}
    heading_terms = _normalize_list(anchors_cfg.get("sectionizer_extra"))

    ordered_entries = _ordered_entries(ctx.paragraph_store or {})
    heading_candidates = _detect_headings(ordered_entries, heading_terms)
    if not heading_candidates:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_headings_detected")

    rebuilt: Dict[str, Dict[str, object]] = {}
    seen_titles: set[str] = set()

    for title, page in heading_candidates:
        title_key = title.strip()
        if not title_key:
            continue
        lowered = title_key.lower()
        if lowered in seen_titles:
            continue
        seen_titles.add(lowered)
        rebuilt[title_key] = {
            "start_page": page,
            "source": "second_pass_ifu_sectionizer",
        }
        if len(rebuilt) >= 20:
            break

    if len(rebuilt) < 2:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="insufficient_headings")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}

    pipeline_info["sections"] = rebuilt

    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    patches_applied = second_pass_bucket.setdefault("patches_applied", [])
    if PATCH_NAME not in patches_applied:
        patches_applied.append(PATCH_NAME)
    applied_list = second_pass_bucket.setdefault("applied", [])
    if PATCH_NAME not in applied_list:
        applied_list.append(PATCH_NAME)
    reasons_list = second_pass_bucket.setdefault("reasons", [])
    reason_label = f"section_salvage_ifu:{{'sections_rebuilt': {len(rebuilt)}}}"
    if reason_label not in reasons_list:
        reasons_list.append(reason_label)

    modifications_bucket = second_pass_bucket.setdefault("modifications", {})
    modifications_bucket["sections_rebuilt"] = modifications_bucket.get("sections_rebuilt", 0) + len(rebuilt)
    meta = second_pass_bucket.setdefault("meta", {})
    meta["sections_rebuilt"] = meta.get("sections_rebuilt", 0) + len(rebuilt)

    pipeline_info["second_pass"] = second_pass_bucket
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"sections_rebuilt": len(rebuilt)},
        reasons=[reason_label],
    )


__all__ = ["apply_ifu_sectionizer_salvage"]
