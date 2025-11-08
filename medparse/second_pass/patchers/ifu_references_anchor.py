"""Second-pass patcher that backfills References/Bibliography anchors for IFUs."""

from __future__ import annotations

import re
from typing import Dict, List, Set

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_references_anchor"
REFERENCE_PATTERN = re.compile(r"\b(references|bibliography|literature)\b", re.IGNORECASE)


def apply_ifu_references_anchor(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    if not getattr(document, "references", None):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_references_detected")

    if pipeline_info.get("references_anchor_backfill"):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="anchor_already_backfilled")

    trigger_present = any(
        "references detected for ifu" in issue.message.lower()
        for issue in ctx.validation_issues
    )
    if ctx.mode == "auto" and not trigger_present:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="auto_mode_no_trigger")

    page_count = getattr(document, "page_count", 0) or 0
    tail_pages = 2
    if isinstance(ctx.config, dict):
        config_block = (
            ctx.config.get("ifu", {})
            .get("references_anchor", {})
        )
        if isinstance(config_block, dict):
            try:
                tail_pages = int(config_block.get("tail_pages", tail_pages))
            except (TypeError, ValueError):
                tail_pages = tail_pages
    tail_pages = max(1, tail_pages)

    candidate_pages: Set[int] = set()
    evidence_map: Dict[int, List[str]] = {}
    for hash_id, entry in ctx.paragraph_store.items():
        page_no = entry.get("page")
        text = entry.get("text")
        if not isinstance(page_no, int) or not isinstance(text, str):
            continue
        if page_count and page_no < max(1, page_count - tail_pages + 1):
            continue
        if REFERENCE_PATTERN.search(text):
            candidate_pages.add(page_no)
            evidence_map.setdefault(page_no, []).append(str(hash_id))

    if not candidate_pages and page_count:
        start_page = max(1, page_count - tail_pages + 1)
        candidate_pages.update(range(start_page, page_count + 1))

    if not candidate_pages:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_reference_pages_detected")

    normalized_pages = sorted(
        {max(1, min(page_count or 1, int(page))) for page in candidate_pages}
    )

    anchor_info = {
        "pages": normalized_pages,
        "source": "second-pass:references_anchor_backfill",
    }
    pipeline_info["references_anchor"] = anchor_info
    pipeline_info["references_anchor_backfill"] = True

    if normalized_pages:
        start_page = normalized_pages[0]
        end_page = normalized_pages[-1]
        sections_map = getattr(document, "sections", None)
        if not isinstance(sections_map, dict):
            sections_map = pipeline_info.get("sections") if isinstance(pipeline_info, dict) else {}
            if not isinstance(sections_map, dict):
                sections_map = {}
        references_section = sections_map.get("references")
        evidence_ids: List[str] = []
        for page in normalized_pages:
            evidence_ids.extend(evidence_map.get(page, []))
        evidence_ids = list(dict.fromkeys(evidence_ids))
        payload = {
            "page_span": [start_page, end_page],
            "source": "second_pass:references_anchor_backfill",
        }
        if evidence_ids:
            payload["evidence_ids"] = evidence_ids
        if isinstance(references_section, dict):
            references_section.setdefault("page_span", payload["page_span"])
            references_section.setdefault("source", payload["source"])
            if evidence_ids:
                existing_ids = references_section.setdefault("evidence_ids", [])
                if isinstance(existing_ids, list):
                    for evidence in evidence_ids:
                        if evidence not in existing_ids:
                            existing_ids.append(evidence)
                else:
                    references_section["evidence_ids"] = evidence_ids
        else:
            sections_map["references"] = payload
        pipeline_info["sections"] = sections_map
        try:
            setattr(document, "sections", sections_map)
        except Exception:
            pass

    patches_applied = second_pass_bucket.setdefault("patches_applied", [])
    if PATCH_NAME not in patches_applied:
        patches_applied.append(PATCH_NAME)

    meta = second_pass_bucket.setdefault("meta", {})
    meta["references_anchor_backfill"] = meta.get("references_anchor_backfill", 0) + 1

    pipeline_info["second_pass"] = second_pass_bucket

    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"references_anchor_backfill": len(candidate_pages)},
        reasons=["references_anchor_backfill"],
    )


__all__ = ["apply_ifu_references_anchor"]
