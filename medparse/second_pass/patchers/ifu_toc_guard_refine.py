"""Second-pass refinement for IFU TOC guard metadata."""

from __future__ import annotations

from typing import Dict, List

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_toc_guard_refine"


def _extract_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _fill_small_gaps(pages: List[int]) -> List[int]:
    if len(pages) < 3:
        return pages
    sorted_pages = sorted(pages)
    gaps = [b - a for a, b in zip(sorted_pages, sorted_pages[1:])]
    max_gap = max(gaps, default=0)
    span = sorted_pages[-1] - sorted_pages[0]
    if max_gap <= 2 and span <= 8:
        return list(range(sorted_pages[0], sorted_pages[-1] + 1))
    return sorted_pages


def apply_ifu_toc_guard_refine(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}

    drop_pages = pipeline_info.get("toc_guard_pages_dropped")
    if not isinstance(drop_pages, list) or not drop_pages:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_toc_drops")

    indications_present = bool(_extract_text(document.indications_for_use))
    contraindications_present = bool(document.contraindications)
    anchor_errors = pipeline_info.get("anchor_bleed_errors") or []

    severity = "info"
    if anchor_errors and not (indications_present or contraindications_present):
        severity = "error"

    normalized_pages: List[int] = []
    seen: set[int] = set()
    for value in drop_pages:
        try:
            page_num = int(value)
        except (TypeError, ValueError):
            continue
        if page_num not in seen:
            seen.add(page_num)
            normalized_pages.append(page_num)

    normalized_pages.sort()
    normalized_pages = _fill_small_gaps(normalized_pages)

    pipeline_info["toc_guard_pages_dropped"] = normalized_pages
    pipeline_info["toc_guard_pages_dropped_count"] = len(normalized_pages)

    toc_guard_info = pipeline_info.setdefault("toc_guard", {})
    if not isinstance(toc_guard_info, dict):
        toc_guard_info = {}
        pipeline_info["toc_guard"] = toc_guard_info
    toc_guard_info["pages_dropped"] = normalized_pages
    toc_guard_info["severity"] = severity

    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    patches_applied = second_pass_bucket.setdefault("patches_applied", [])
    if PATCH_NAME not in patches_applied:
        patches_applied.append(PATCH_NAME)
    applied_list = second_pass_bucket.setdefault("applied", [])
    if PATCH_NAME not in applied_list:
        applied_list.append(PATCH_NAME)
    reasons_list = second_pass_bucket.setdefault("reasons", [])
    reason_label = f"toc_guard_refine:severity={severity}"
    if reason_label not in reasons_list:
        reasons_list.append(reason_label)

    pipeline_info["toc_guard_severity"] = severity
    modifications_bucket = second_pass_bucket.setdefault("modifications", {})
    modifications_bucket["toc_guard_pages_dropped"] = len(normalized_pages)
    pipeline_info["second_pass"] = second_pass_bucket
    document.pipeline_info = pipeline_info
    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"toc_guard_pages_dropped": len(normalized_pages)},
        reasons=[reason_label],
    )


__all__ = ["apply_ifu_toc_guard_refine"]
