"""Backward-compatible IFU anchor utilities built on the new anchor module."""

from __future__ import annotations

import re
from typing import Callable, Dict, Sequence, List, Set

from medparse.ifu.anchors import (
    AnchorBleedError,
    resolve_anchor_map,
    resolve_toc_guard,
    slice_section,
    strip_toc,
    normalize_bullets,
    DEFAULT_SECTION_ANCHORS,
    Section,
    is_toc_like_para,
)
from medparse.ifu.manufacturers import get_manufacturer_rules
from medparse.ifu.toc_guard import detect_first_chapter_page
from medparse.ingest.models import PageData
from medparse.normalize.ifu_sections import (
    clean_section_text,
    parse_contraindications,
    sanitize_adverse_events,
)
from medparse.normalize.ifu_small import apply_small_leaflet_policy
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)


INDICATION_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\s+.*indications?\s+for\s+use\b", re.IGNORECASE)


CLINICAL_ANCHORS = DEFAULT_SECTION_ANCHORS


def extract_clinical_block(
    pages: Sequence[PageData],
    *,
    start: Sequence[str],
    stops: Sequence[str] | None = None,
    toc_guard_settings: Dict[str, object] | None = None,
) -> str | None:
    guard = resolve_toc_guard(toc_guard_settings or {}, manufacturer=None)
    filtered_pages, guard_report = strip_toc(pages, guard)
    section = slice_section(
        filtered_pages,
        start,
        stops or [],
        toc_guard=False,
        guard_config=guard,
        toc_mask=guard_report.pages_dropped if guard_report else None,
    )
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
    filtered_pages, guard_report = strip_toc(pages, guard)
    guard_metrics = guard_report.to_metrics()
    anchor_overrides = settings.get("anchors") or {}
    anchors = resolve_anchor_map(anchor_overrides, manufacturer=manufacturer)

    threshold_raw = settings.get("small_ifu_threshold")
    small_ifu_threshold = 4
    if threshold_raw is not None:
        try:
            small_ifu_threshold = max(1, int(threshold_raw))
        except (TypeError, ValueError):
            LOGGER.debug("Invalid small_ifu_threshold override: %r", threshold_raw)
    is_small_ifu = len(pages) <= small_ifu_threshold
    if is_small_ifu:
        LOGGER.debug("Small IFU detected (%d pages, threshold=%d)", len(pages), small_ifu_threshold)

    manufacturer_normalized = (manufacturer or "").strip().upper()
    first_content_page = None
    manufacturer_rules = get_manufacturer_rules(manufacturer)
    first_content_page = None
    if manufacturer_normalized.startswith("INTUITIVE"):
        first_content_page = detect_first_chapter_page(filtered_pages)
        if first_content_page:
            manufacturer_rules = dict(manufacturer_rules)
            existing_min = manufacturer_rules.get("min_anchor_page")
            if isinstance(existing_min, int):
                manufacturer_rules["min_anchor_page"] = max(existing_min, first_content_page)
            else:
                manufacturer_rules["min_anchor_page"] = first_content_page

    overrides_cfg = settings.get("manufacturer_overrides") if isinstance(settings, dict) else {}
    if manufacturer_normalized and isinstance(overrides_cfg, dict):
        for key, value in overrides_cfg.items():
            if key.strip().upper() == manufacturer_normalized and isinstance(value, dict):
                min_page_override = value.get("min_anchor_page")
                if isinstance(min_page_override, int):
                    manufacturer_rules = dict(manufacturer_rules)
                    existing_min = manufacturer_rules.get("min_anchor_page")
                    if isinstance(existing_min, int):
                        manufacturer_rules["min_anchor_page"] = max(existing_min, int(min_page_override))
                    else:
                        manufacturer_rules["min_anchor_page"] = int(min_page_override)
                break

    # Small IFU rule: 2-4 page leaflets
    anchors_bleed: Dict[str, int] = {}
    small_ifu_applied = False

    errors = ifu_json.setdefault("_anchor_errors", [])
    error_fields = ifu_json.setdefault("_anchor_error_fields", [])
    section_spans: Dict[str, Dict[str, int]] = {}

    toc_mask_values = guard_report.pages_dropped if guard_report else []
    toc_mask_set: Set[int] = set()
    for value in toc_mask_values or []:
        try:
            toc_mask_set.add(int(value))
        except (TypeError, ValueError):
            continue

    for field, config in anchors.items():
        start = config.get("start", [])
        stops = config.get("stops", [])
        section_validator = None
        if field == "indications_for_use" and manufacturer_normalized.startswith("INTUITIVE"):
            section_validator = _build_indications_validator(toc_mask_set)
        try:
            section = slice_section(
                filtered_pages,
                start,
                stops,
                toc_guard=False,
                guard_config=guard,
                min_start_page=manufacturer_rules.get("min_anchor_page") if isinstance(manufacturer_rules, dict) else None,
                field_name=field,
                manufacturer_rules=manufacturer_rules if isinstance(manufacturer_rules, dict) else None,
                toc_mask=toc_mask_values,
                section_validator=section_validator,
            )
            if not section.text and toc_mask_values:
                section = slice_section(
                    filtered_pages,
                    start,
                    stops,
                    toc_guard=False,
                    guard_config=guard,
                    min_start_page=manufacturer_rules.get("min_anchor_page") if isinstance(manufacturer_rules, dict) else None,
                    field_name=field,
                    manufacturer_rules=manufacturer_rules if isinstance(manufacturer_rules, dict) else None,
                    toc_mask=None,
                    section_validator=section_validator,
                )
        except AnchorBleedError as exc:
            LOGGER.debug("Skipping %s due to TOC bleed: %s", field, exc)
            errors.append(str(exc))
            error_fields.append(field)
            continue

        if not section.text:
            continue

        if section.trimmed_prefix:
            anchors_bleed[field] = section.trimmed_prefix

        span_payload: Dict[str, int] = {}
        if isinstance(section.start_page, int):
            span_payload["start_page"] = section.start_page
        if isinstance(section.end_page, int):
            span_payload["end_page"] = section.end_page
        if span_payload:
            section_spans[field] = span_payload

        block = normalize_bullets(section.text)
        block = clean_section_text(block)
        if not block:
            continue

        if field == "contraindications":
            parsed = parse_contraindications(block)
            if parsed:
                ifu_json[field] = parsed
            elif field not in ifu_json:
                ifu_json[field] = []
            continue

        if field == "clinical_risks_and_benefits":
            risks = sanitize_adverse_events(block)
            if not risks:
                continue
            existing = ifu_json.get("adverse_events")
            if not isinstance(existing, list):
                existing_list = [existing] if isinstance(existing, str) and existing else []
            else:
                existing_list = existing
            merged = _merge_lists(existing_list, risks)
            if merged:
                ifu_json["adverse_events"] = merged
            continue

        if field == "adverse_events":
            parsed = sanitize_adverse_events(block)
            if parsed:
                ifu_json[field] = parsed
            elif field not in ifu_json:
                ifu_json[field] = []
            continue

        if field in {"intended_use", "intended_user", "intended_patient_population", "indications_for_use"}:
            ifu_json[field] = block
            continue

        ifu_json[field] = block

    policy = settings.get("small_leaflet_policy") if isinstance(settings, dict) else None
    if is_small_ifu:
        applied_policy = apply_small_leaflet_policy(
            ifu_json,
            policy=policy,
            page_count=len(pages),
            pages=filtered_pages,
        )
        if applied_policy:
            LOGGER.debug("Small IFU policy applied: %s", policy or "<default>")
            small_ifu_applied = True

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

    if "clinical_risks_and_benefits" in ifu_json:
        ifu_json.pop("clinical_risks_and_benefits", None)

    toc_info: Dict[str, object] = {
        "enabled": bool(guard_metrics.get("enabled", guard.enabled)),
        "pages_dropped": sorted(guard_metrics.get("pages_dropped", [])),
        "pages_dropped_count": guard_metrics.get("pages_dropped_count", 0),
        "config": guard.as_dict(),
        "small_ifu_threshold": small_ifu_threshold,
        "small_ifu_fallback_applied": bool(small_ifu_applied),
    }
    if toc_mask_set:
        toc_info["toc_mask"] = sorted(toc_mask_set)
    if guard_metrics.get("pages_considered") is not None:
        toc_info["pages_considered"] = guard_metrics.get("pages_considered")
    if anchors_bleed:
        toc_info["anchors_bleed"] = anchors_bleed
    if manufacturer_rules:
        toc_info["manufacturer_rules"] = {key: value for key, value in manufacturer_rules.items() if value}

    if section_spans:
        ifu_json["_anchor_spans"] = section_spans
        toc_info["section_spans"] = section_spans

    return toc_info


def _build_indications_validator(toc_mask: Set[int]) -> Callable[[Section], bool]:
    mask = {int(page) for page in toc_mask if isinstance(page, int)}

    def _validator(section: Section) -> bool:
        if section.start_page is None:
            return False
        if mask and section.start_page in mask:
            return False
        lines = section.lines or []
        if not lines:
            return False
        heading = lines[0].strip()
        if not INDICATION_HEADING_RE.search(heading):
            return False
        body_lines = [line for line in lines[1:] if line.strip() and not is_toc_like_para(line)]
        return len(body_lines) >= 2

    return _validator


def _merge_lists(first: List[str], second: List[str]) -> List[str]:
    combined: List[str] = []
    seen: set[str] = set()
    for collection in (first, second):
        for item in collection:
            normalized = item.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            combined.append(normalized)
    return combined


__all__ = ["AnchorBleedError", "extract_clinical_block", "lift_ifu_clinical_fields"]
