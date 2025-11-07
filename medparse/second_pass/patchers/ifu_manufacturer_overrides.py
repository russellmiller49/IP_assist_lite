"""Second-pass patcher applying manufacturer-aware overrides for IFUs."""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_manufacturer_overrides"


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def apply_ifu_manufacturer_overrides(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    manufacturer = (document.manufacturer or "").strip()
    if not manufacturer:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_manufacturer")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    sections = getattr(document, "sections", None)
    if not isinstance(sections, dict) or not sections:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_sections")

    config = {}
    if isinstance(ctx.config, dict):
        config = ctx.config.get("manufacturer_overrides", {})
    if not isinstance(config, dict):
        config = {}

    normalized = _normalize(manufacturer)
    override = None
    for key, value in config.items():
        if normalized == _normalize(str(key)):
            override = value
            break
    if not isinstance(override, dict):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_override")

    skip_tokens = override.get("skip_anchors") or []
    if not isinstance(skip_tokens, list):
        skip_tokens = []
    skip_tokens = [str(token).lower() for token in skip_tokens if token]
    if not skip_tokens:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_skip_tokens")

    reordered = OrderedDict()
    skipped_entries = OrderedDict()

    for key, value in sections.items():
        title = ""
        if isinstance(value, dict):
            title = str(value.get("title") or key)
        else:
            title = str(key)
        title_lower = title.lower()
        if any(token in title_lower for token in skip_tokens):
            skipped_entries[key] = value
        else:
            reordered[key] = value

    if not skipped_entries:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_sections_skipped")

    for key, value in skipped_entries.items():
        reordered[key] = value

    if list(reordered.keys()) == list(sections.keys()):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="order_unchanged")

    document.sections = dict(reordered)
    pipeline_info.setdefault("manufacturer_overrides_applied", []).append(manufacturer)
    pipeline_info.setdefault("second_pass", {}).setdefault("patches_applied", [])
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"sections_reordered": len(skipped_entries)},
        reasons=["manufacturer_anchor_override"],
    )
