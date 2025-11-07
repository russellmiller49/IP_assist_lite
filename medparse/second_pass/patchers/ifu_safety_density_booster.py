"""Second-pass patcher that increases IFU safety block density."""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from medparse.schema.common import BaseDocument, EvidenceSpan
from medparse.schema.ifu import IFUDocument, SafetyBlock

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_safety_density_booster"

SAFETY_PREFIXES = (
    "warning",
    "caution",
    "danger",
    "notice",
    "important",
    "note",
    "attention",
)

ICON_PATTERN = re.compile(r"[⚠‼❗!△▲]")
SAFETY_KEYWORDS = (
    "warning",
    "caution",
    "important",
    "notice",
    "attention",
    "hazard",
    "danger",
    "safety",
)


def _ordered_entries(paragraph_store: Dict[str, Dict[str, object]]) -> List[Tuple[int, Dict[str, object]]]:
    ordered: List[Tuple[int, Dict[str, object]]] = []
    for hash_id, entry in paragraph_store.items():
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        orders = entry.get("order") or []
        try:
            order_index = min(int(value) for value in orders) if orders else 10**6
        except (TypeError, ValueError):
            order_index = 10**6
        ordered.append((order_index, {**entry, "hash": hash_id}))
    ordered.sort(key=lambda item: item[0])
    return ordered


def _infer_level(text: str) -> str:
    lowered = text.lower()
    for prefix in SAFETY_PREFIXES:
        if lowered.startswith(prefix):
            level = "note" if prefix == "note" else prefix
            return level if level in ALLOWED_LEVELS else "notice"
    if ICON_PATTERN.search(text):
        return "warning"
    return "notice"


def _bounded_page(page: int, page_count: Optional[int]) -> Optional[int]:
    if page < 1:
        return None
    if page_count and page > page_count:
        return page_count
    return page


def _add_page_with_radius(pages: Set[int], page: Optional[int], radius: int, page_count: Optional[int]) -> None:
    if page is None:
        return
    for offset in range(-radius, radius + 1):
        candidate = page + offset
        bounded = _bounded_page(candidate, page_count)
        if bounded is not None:
            pages.add(bounded)


def _collect_section_pages(
    document: IFUDocument,
    section_names: Set[str],
) -> Set[int]:
    pages: Set[int] = set()
    page_count = getattr(document, "page_count", None)
    section_map = getattr(document, "sections", None)
    if not isinstance(section_map, dict):
        pipeline_info = getattr(document, "pipeline_info", {}) or {}
        section_map = pipeline_info.get("sections") if isinstance(pipeline_info, dict) else {}
    if isinstance(section_map, dict):
        for key, value in section_map.items():
            if not isinstance(value, dict):
                continue
            key_lower = key.lower()
            if key_lower not in section_names:
                continue
            start = value.get("start_page")
            end = value.get("end_page", start)
            try:
                start_page = int(start) if start is not None else None
            except (TypeError, ValueError):
                start_page = None
            try:
                end_page = int(end) if end is not None else None
            except (TypeError, ValueError):
                end_page = start_page
            if start_page is None:
                continue
            if end_page is None:
                end_page = start_page
            for page in range(start_page, end_page + 1):
                bounded = _bounded_page(page, page_count)
                if bounded is not None:
                    pages.add(bounded)
    return pages


def _collect_keyword_pages(
    paragraph_store: Dict[str, Dict[str, object]],
    keywords: Set[str],
    *,
    radius: int,
    page_count: Optional[int],
) -> Set[int]:
    pages: Set[int] = set()
    if not isinstance(paragraph_store, dict):
        return pages
    for entry in paragraph_store.values():
        page = entry.get("page")
        if not isinstance(page, int):
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lowered = text.lower()
        if any(keyword in lowered for keyword in keywords):
            _add_page_with_radius(pages, page, radius, page_count)
    return pages


def _determine_target_pages(document: IFUDocument, ctx: SecondPassContext) -> Set[int]:
    page_count = getattr(document, "page_count", None)
    target_pages = set()
    target_pages.update(_collect_section_pages(document, {"warnings", "warning", "cautions", "notes"}))
    if isinstance(ctx.paragraph_store, dict):
        target_pages.update(
            _collect_keyword_pages(
                ctx.paragraph_store,
                {"warnings", "warning", "caution", "cautions", "notes"},
                radius=0,
                page_count=page_count,
            )
        )
        target_pages.update(
            _collect_keyword_pages(
                ctx.paragraph_store,
                {"sterilization", "system setup", "setup"},
                radius=2,
                page_count=page_count,
            )
        )
    bounded_pages = {
        page
        for page in target_pages
        if page >= 1 and (not page_count or page <= page_count)
    }
    return bounded_pages


def _looks_like_safety(text: str) -> Optional[str]:
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    lowered = stripped.lower()
    if ICON_PATTERN.match(stripped) or ICON_PATTERN.search(stripped[:3]):
        return "icon"
    colon_index = stripped.find(":")
    if colon_index != -1 and colon_index <= 10:
        prefix = stripped[:colon_index].strip().lower()
        if prefix.startswith(("warning", "caution", "note", "danger", "important")):
            return "heading"
    if re.match(r"^\d+(?:\.\d+)*\s+(warning|caution|note)", stripped, re.IGNORECASE):
        return "heading"
    if any(lowered.startswith(prefix) for prefix in SAFETY_PREFIXES):
        return "heading"
    if any(keyword in lowered for keyword in SAFETY_KEYWORDS):
        return "heading"
    if stripped.isupper() and len(stripped.split()) <= 6:
        return "heading"
    return None


def _similar_text(candidate: str, existing: List[str], threshold: float) -> bool:
    normalized = candidate.strip().lower()
    for text in existing:
        if normalized == text:
            return True
        if SequenceMatcher(None, normalized, text).ratio() >= threshold:
            return True
    return False


def apply_ifu_safety_density_booster(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    safety_blocks = list(document.safety_blocks or [])
    expected_min = None
    if isinstance(pipeline_info, dict):
        try:
            expected_min = int(pipeline_info.get("safety_expected_min"))
        except (TypeError, ValueError):
            expected_min = None
    if expected_min is None:
        expected_min = 20

    booster_cfg = {}
    if isinstance(ctx.config, dict):
        booster_cfg = (
            ctx.config.get("ifu", {})
            .get("safety", {})
            .get("booster", {})
        )
    dedupe_ratio = 0.9
    max_added = 20
    if isinstance(booster_cfg, dict):
        try:
            dedupe_ratio = float(booster_cfg.get("dedupe_ratio", dedupe_ratio))
        except (TypeError, ValueError):
            dedupe_ratio = 0.9
        try:
            max_added = int(booster_cfg.get("max_added", max_added))
        except (TypeError, ValueError):
            max_added = 20
    max_added = max(1, max_added)

    if len(safety_blocks) >= expected_min and ctx.mode != "always":
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="density_ok")

    triggers = [
        issue
        for issue in ctx.validation_issues
        if "expected at least" in issue.message.lower() and "safety" in issue.message.lower()
    ]
    if ctx.mode == "auto" and not triggers and len(safety_blocks) >= expected_min:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="auto_mode_no_trigger")

    existing_texts = {block.text.strip().lower() for block in safety_blocks if getattr(block, "text", None)}
    similarity_cache = list(existing_texts)
    existing_hashes = {getattr(block, "hash", None) for block in safety_blocks if getattr(block, "hash", None)}
    additions = 0
    ordered_entries = _ordered_entries(ctx.paragraph_store)
    target_pages = _determine_target_pages(document, ctx)
    page_count = getattr(document, "page_count", None)
    added_hashes: Set[str] = set()

    for _, entry in ordered_entries:
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        page = entry.get("page")
        if target_pages and (not isinstance(page, int) or page not in target_pages):
            continue
        source_hint = _looks_like_safety(stripped)
        if not source_hint:
            continue
        lowered = stripped.lower()
        if lowered in existing_texts or _similar_text(stripped, similarity_cache, dedupe_ratio):
            continue
        entry_hash = entry.get("hash")
        if isinstance(entry_hash, str) and entry_hash.strip():
            normalized_hash = entry_hash.strip()
        else:
            normalized_hash = hashlib.sha1(f"{lowered}|{entry.get('page')}".encode("utf-8")).hexdigest()
        if normalized_hash in existing_hashes or normalized_hash in added_hashes:
            continue
        level = _infer_level(stripped)
        source_value = source_hint if source_hint in {"icon", "heading"} else "heading"
        evidence = EvidenceSpan(
            text=stripped if len(stripped) <= 400 else stripped[:397] + "...",
            page=entry.get("page"),
            hash=normalized_hash,
        )
        safety_block = SafetyBlock(level=level, text=stripped, evidence=evidence)
        safety_block.source = source_value
        safety_block.category = "second_pass:safety_density_boost"
        bounded_page = _bounded_page(entry.get("page"), page_count)
        if bounded_page is not None:
            safety_block.page = bounded_page
        safety_block.hash = normalized_hash
        existing_hashes.add(normalized_hash)
        added_hashes.add(normalized_hash)
        safety_blocks.append(safety_block)
        existing_texts.add(lowered)
        similarity_cache.append(lowered)
        additions += 1
        if additions >= max_added:
            break
        if len(safety_blocks) >= expected_min and ctx.mode != "always":
            break

    if additions == 0:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_new_blocks")

    document.safety_blocks = safety_blocks
    pipeline_info["safety_blocks_found"] = len(safety_blocks)
    pipeline_info["safety_density_boost_applied"] = True
    pipeline_info["safety_blocks_added"] = pipeline_info.get("safety_blocks_added", 0) + additions
    patches_applied = second_pass_bucket.setdefault("patches_applied", [])
    if PATCH_NAME not in patches_applied:
        patches_applied.append(PATCH_NAME)
    meta = second_pass_bucket.setdefault("meta", {})
    meta["safety_blocks_added"] = meta.get("safety_blocks_added", 0) + additions
    pipeline_info["second_pass"] = second_pass_bucket
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"safety_blocks_added": additions},
        reasons=["safety_density_boost"],
    )
ALLOWED_LEVELS = {"danger", "warning", "caution", "notice", "note", "attention"}
