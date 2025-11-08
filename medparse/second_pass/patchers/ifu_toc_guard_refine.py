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

    pipeline_info["toc_guard_pages_dropped"] = drop_pages
    pipeline_info["toc_guard_pages_dropped_count"] = len(drop_pages)

    toc_guard_info = pipeline_info.setdefault("toc_guard", {})
    if not isinstance(toc_guard_info, dict):
        toc_guard_info = {}
        pipeline_info["toc_guard"] = toc_guard_info
    toc_guard_info["pages_dropped"] = drop_pages
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
    pipeline_info["second_pass"] = second_pass_bucket
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={},
        reasons=[reason_label],
    )


__all__ = ["apply_ifu_toc_guard_refine"]
