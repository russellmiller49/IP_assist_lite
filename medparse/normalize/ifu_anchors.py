"""Backward-compatible IFU anchor utilities built on the new anchor module."""

from __future__ import annotations

import re
from typing import Dict, Sequence

from medparse.ifu.anchors import (
    AnchorBleedError,
    resolve_anchor_map,
    resolve_toc_guard,
    slice_section,
    strip_toc,
    normalize_bullets,
    DEFAULT_SECTION_ANCHORS,
)
from medparse.ingest.models import PageData
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)


CLINICAL_ANCHORS = DEFAULT_SECTION_ANCHORS


def extract_clinical_block(
    pages: Sequence[PageData],
    *,
    start: Sequence[str],
    stops: Sequence[str] | None = None,
    toc_guard_settings: Dict[str, object] | None = None,
) -> str | None:
    guard = resolve_toc_guard(toc_guard_settings or {}, manufacturer=None)
    filtered_pages, _ = strip_toc(pages, guard)
    section = slice_section(filtered_pages, start, stops or [], toc_guard=False, guard_config=guard)
    if not section.text:
        return None
    return normalize_bullets(section.text)


def lift_ifu_clinical_fields(
    pages: Sequence[PageData],
    ifu_json: dict,
    *,
    settings: Dict[str, object] | None = None,
    manufacturer: str | None = None,
) -> Dict[str, object]:
    settings = settings or {}
    guard = resolve_toc_guard(settings, manufacturer)
    filtered_pages, dropped_pages = strip_toc(pages, guard)
    anchor_overrides = settings.get("anchors") or {}
    anchors = resolve_anchor_map(anchor_overrides)

    errors = ifu_json.setdefault("_anchor_errors", [])
    error_fields = ifu_json.setdefault("_anchor_error_fields", [])

    for field, config in anchors.items():
        start = config.get("start", [])
        stops = config.get("stops", [])
        try:
            section = slice_section(filtered_pages, start, stops, toc_guard=False, guard_config=guard)
        except AnchorBleedError as exc:
            LOGGER.debug("Skipping %s due to TOC bleed: %s", field, exc)
            errors.append(str(exc))
            error_fields.append(field)
            continue

        if not section.text:
            continue

        block = normalize_bullets(section.text)
        if field in {"contraindications", "adverse_events"}:
            ifu_json[field] = [block] if block else []
        else:
            ifu_json[field] = block

    # Rx-only detection for intended_user
    combined_text = "\n".join(page.text for page in pages if page.text)
    if re.search(r"\bRx\s*only\b", combined_text, re.IGNORECASE):
        ifu_json.setdefault("intended_user", "Rx only")

    for key in ("contraindications", "adverse_events"):
        value = ifu_json.get(key)
        if isinstance(value, str) and value:
            ifu_json[key] = [value]
        elif not value:
            ifu_json[key] = []

    return {
        "enabled": guard.enabled,
        "pages_dropped": sorted(dropped_pages),
        "density_threshold": guard.density_threshold,
        "dot_leader_min": guard.dot_leader_min,
        "page_number_ratio": guard.page_number_ratio,
    }


__all__ = ["AnchorBleedError", "extract_clinical_block", "lift_ifu_clinical_fields"]
