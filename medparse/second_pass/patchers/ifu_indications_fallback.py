"""Second-pass patcher that backfills IFU indications/intended-use fields."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_indications_fallback"

HEADLINE_RE = re.compile(r"^\s*(intended\s+(?:use|purpose)|for\s+use\s+in)\b", re.IGNORECASE)
INLINE_RE = re.compile(r"\b(this\s+device\s+is\s+used\s+to\b.+)", re.IGNORECASE)
SMALL_LEAFLET_MANUFACTURERS = {
    "OLYMPUS",
    "OLYMPUS CORPORATION",
    "OLYMPUS AMERICA INC.",
    "OLYMPUS MEDICAL",  # fallback alias
}


def _ordered_entries(paragraph_store: Dict[str, Dict[str, object]]) -> List[Tuple[int, str]]:
    ordered: List[Tuple[int, str]] = []
    for entry in paragraph_store.values():
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        order_values = entry.get("order") or []
        try:
            order_index = min(int(value) for value in order_values) if order_values else 10**6
        except (TypeError, ValueError):
            order_index = 10**6
        ordered.append((order_index, text.strip()))
    ordered.sort(key=lambda item: item[0])
    return ordered


def _extract_candidate_text(paragraphs: List[Tuple[int, str]]) -> Optional[str]:
    for _, text in paragraphs:
        if not text:
            continue
        if HEADLINE_RE.match(text):
            return text
        inline = INLINE_RE.search(text)
        if inline:
            return inline.group(1).strip()
    return None


def apply_ifu_indications_fallback(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    if document.indications_for_use:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="indications_present")

    triggers = [
        issue
        for issue in ctx.validation_issues
        if "missing required field 'indications_for_use'" in issue.message.lower()
    ]
    if ctx.mode == "auto" and not triggers:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="auto_mode_no_trigger")

    manufacturer = (document.manufacturer or "").strip().upper()
    early_hit = False
    for entry in ctx.paragraph_store.values():
        page_no = entry.get("page")
        if not isinstance(page_no, int) or page_no > 3:
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lowered = text.lower()
        if HEADLINE_RE.search(text) or INLINE_RE.search(text) or "indications for use" in lowered or "intended use" in lowered:
            early_hit = True
            break

    if not early_hit and manufacturer not in SMALL_LEAFLET_MANUFACTURERS:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_early_synonym_trigger")

    if (
        document.page_count
        and document.page_count > 4
        and (document.doc_subtype or "").lower() != "leaflet"
        and manufacturer not in SMALL_LEAFLET_MANUFACTURERS
    ):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="page_count_too_high")

    ordered = _ordered_entries(ctx.paragraph_store)
    candidate = _extract_candidate_text(ordered)
    if not candidate:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_candidate_text")

    document.indications_for_use = candidate.strip()
    pipeline_info.setdefault("indications_fallback_provenance", "fallback_small_leaflet")
    pipeline_info.setdefault("second_pass", {}).setdefault("patches_applied", [])
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"indications_backfilled": 1},
        reasons=["fallback_small_leaflet"],
    )
