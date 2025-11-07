"""Second-pass patcher protecting IFU sections from TOC bleed."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_toc_bleed_guard"

DEFAULT_DROP_PATTERNS = [
    r"^\s*\d+(?:\.\d+)*\s+.*[-–.…]{2,}\s*\d+\s*$",
    r"^\s*[A-Z][A-Za-z ]+\s+[-–.…]{2,}\s*\d+\s*$",
]


def _compile_patterns(config: Dict[str, object]) -> List[re.Pattern]:
    patterns = config.get("drop_patterns", []) if isinstance(config, dict) else []
    if not isinstance(patterns, list):
        patterns = []
    raw_patterns = patterns or DEFAULT_DROP_PATTERNS
    compiled: List[re.Pattern] = []
    for pattern in raw_patterns:
        try:
            compiled.append(re.compile(str(pattern)))
        except re.error:
            continue
    return compiled


def _detect_bleed_pages(paragraph_store: Dict[str, Dict[str, object]], patterns: List[re.Pattern]) -> Dict[int, int]:
    hits: Dict[int, int] = {}
    for entry in paragraph_store.values():
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        page = entry.get("page")
        if not isinstance(page, int):
            continue
        stripped = text.strip()
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in patterns):
            hits[page] = hits.get(page, 0) + 1
    return hits


def apply_ifu_toc_bleed_guard(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    triggers = [
        issue
        for issue in ctx.validation_issues
        if "toc bleed" in issue.message.lower() or "clinical anchor bleed" in issue.message.lower()
    ]
    if ctx.mode == "auto" and not triggers:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="auto_mode_no_trigger")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    sections_attr = getattr(document, "sections", None)
    target_sections = sections_attr if isinstance(sections_attr, dict) and sections_attr else None
    sections_from_pipeline = False
    if target_sections is None:
        pipeline_sections = pipeline_info.get("sections")
        if isinstance(pipeline_sections, dict) and pipeline_sections:
            target_sections = pipeline_sections
            sections_from_pipeline = True
    if not isinstance(target_sections, dict) or not target_sections:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_sections")

    toc_config = ctx.config.get("toc_guard", {}) if isinstance(ctx.config, dict) else {}
    patterns = _compile_patterns(toc_config if isinstance(toc_config, dict) else {})
    if not patterns:
        patterns = [re.compile(pattern) for pattern in DEFAULT_DROP_PATTERNS]

    bleed_hits = _detect_bleed_pages(ctx.paragraph_store, patterns)
    if not bleed_hits:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_bleed_pages_detected")

    threshold = max(1, int(toc_config.get("min_hits", 2))) if isinstance(toc_config, dict) else 2
    suspect_pages = {page for page, count in bleed_hits.items() if count >= threshold}
    if not suspect_pages:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_suspect_pages")

    adjustments: List[Tuple[str, int, int]] = []
    for key, value in target_sections.items():
        if not isinstance(value, dict):
            continue
        start_page = value.get("start_page")
        if not isinstance(start_page, int):
            continue
        if start_page not in suspect_pages:
            continue
        new_page = start_page + 1
        if document.page_count and new_page > document.page_count:
            continue
        value["start_page"] = new_page
        adjustments.append((key, start_page, new_page))

    if not adjustments:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_adjustments")

    pipeline_info.setdefault("toc_guard_adjustments_detail", []).extend(
        {"section": key, "from_page": old, "to_page": new} for key, old, new in adjustments
    )
    pipeline_info["toc_guard_adjustments"] = pipeline_info.get("toc_guard_adjustments", 0) + len(adjustments)
    pipeline_info.setdefault("second_pass", {}).setdefault("patches_applied", [])
    if sections_from_pipeline:
        pipeline_info["sections"] = target_sections
    else:
        setattr(document, "sections", target_sections)
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"sections_reanchored": len(adjustments)},
        reasons=["toc_bleed_guard"],
    )
