"""Backfill safety metadata from list paragraphs for thin IFU manuals."""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from medparse.schema.common import EvidenceSpan
from medparse.schema.ifu import IFUDocument, SafetyBlock

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_safety_typing"

WARNING_TERMS = ("hazard", "danger", "injury", "risk", "critical")
CAUTION_TERMS = ("carefully", "ensure", "prevent", "handle", "avoid", "do not", "never")
NOTE_TERMS = ("note", "important", "tip")


def apply_ifu_safety_typing(document: IFUDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    enabled = True
    if isinstance(ctx.config, dict):
        ifu_cfg = ctx.config.get("ifu") if isinstance(ctx.config.get("ifu"), dict) else {}
        safety_cfg = ifu_cfg.get("safety_typing", {}) if isinstance(ifu_cfg, dict) else {}
        enabled = bool(safety_cfg.get("enabled", True))
    if not enabled:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="disabled")

    page_count = getattr(document, "page_count", None)
    if isinstance(page_count, int) and page_count > 40:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="page_threshold")

    paragraph_store = ctx.paragraph_store or {}
    list_entries = _collect_list_entries(paragraph_store)
    if not list_entries:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_list_paragraphs")

    existing_hashes = {
        block.hash for block in getattr(document, "safety_blocks", []) or [] if getattr(block, "hash", None)
    }
    additions: List[SafetyBlock] = []
    sections_meta = _section_map(document)

    for entry in list_entries:
        page = entry.get("page")
        if not isinstance(page, int):
            continue
        section_title = _section_for_page(sections_meta, page)
        for item in entry.get("lists", []):
            text = str(item or "").strip()
            if not text:
                continue
            block_hash = _hash_block(text, page)
            if block_hash in existing_hashes:
                continue
            level = _infer_level(text, section_title)
            evidence = EvidenceSpan(
                text=text[:200],
                page=page,
                confidence=0.6,
            )
            block = SafetyBlock(
                level=level,
                severity=_map_severity(level),
                title=section_title or level.title(),
                text=text,
                page=page,
                hash=block_hash,
                category="second_pass:safety_typing",
                source="heading",
                evidence=evidence,
            )
            additions.append(block)
            existing_hashes.add(block_hash)

    if not additions:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_candidates")

    document.safety_blocks.extend(additions)
    _update_safety_metrics(document, len(additions))

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"safety_blocks_typed": len(additions)},
        reasons=["list_backfill"],
    )


def _collect_list_entries(paragraph_store: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    for entry in paragraph_store.values():
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "list":
            continue
        lists = entry.get("lists")
        if not isinstance(lists, list) or not lists:
            continue
        entries.append(entry)
    return entries


def _section_map(document: IFUDocument) -> List[Tuple[int, str]]:
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    sections = pipeline_info.get("sections") if isinstance(pipeline_info, dict) else {}
    if not isinstance(sections, dict):
        return []
    mapping: List[Tuple[int, str]] = []
    for title, meta in sections.items():
        if not isinstance(meta, dict):
            continue
        start_page = meta.get("start_page")
        try:
            page_num = int(start_page)
        except (TypeError, ValueError):
            continue
        mapping.append((page_num, str(title)))
    mapping.sort(key=lambda item: item[0])
    return mapping


def _section_for_page(sections: List[Tuple[int, str]], page: int) -> Optional[str]:
    current: Optional[str] = None
    for start_page, title in sections:
        if start_page <= page:
            current = title
        else:
            break
    return current


def _infer_level(text: str, section_title: Optional[str]) -> str:
    lowered = text.lower()
    if any(term in lowered for term in WARNING_TERMS) or "warning" in lowered:
        return "warning"
    if any(term in lowered for term in CAUTION_TERMS) or "caution" in lowered:
        return "caution"
    if any(term in lowered for term in NOTE_TERMS):
        return "note"
    if section_title:
        lowered_section = section_title.lower()
        if "warning" in lowered_section:
            return "warning"
        if "caution" in lowered_section or "reprocessing" in lowered_section:
            return "caution"
        if "note" in lowered_section or "information" in lowered_section:
            return "note"
    if "do not" in lowered:
        return "caution"
    return "note"


def _map_severity(level: str) -> str:
    if level == "warning":
        return "warning"
    if level == "caution":
        return "caution"
    return "note"


def _hash_block(text: str, page: int) -> str:
    digest = hashlib.sha1(f"{page}:{text}".encode("utf-8")).hexdigest()
    return digest[:16]


def _update_safety_metrics(document: IFUDocument, added: int) -> None:
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    document.pipeline_info = pipeline_info
    total = len(document.safety_blocks)
    pipeline_info["safety_found"] = total
    pipeline_info["safety_blocks_found"] = total
    existing_added = pipeline_info.get("safety_blocks_added", 0)
    try:
        pipeline_info["safety_blocks_added"] = int(existing_added) + added
    except (TypeError, ValueError):
        pipeline_info["safety_blocks_added"] = added
    expected = pipeline_info.get("safety_expected_min")
    try:
        expected_min = int(expected)
    except (TypeError, ValueError):
        expected_min = None
    if expected_min is not None:
        pipeline_info["safety_gap"] = max(0, expected_min - total)
        pipeline_info["safety_status"] = "ok" if total >= expected_min else "low"


__all__ = ["apply_ifu_safety_typing"]
