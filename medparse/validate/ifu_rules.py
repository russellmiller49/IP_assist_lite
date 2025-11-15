"""IFU-specific validation helpers."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Literal, Optional

import yaml

from medparse.config import ExtractionConfig, FrozenNamespace
from medparse.schema.ifu import IFUDocument
from medparse.ifu.safety_thresholds import expected_safety_with_source, get_safety_thresholds
from medparse.ifu.revision import sync_revision_status

SAFETY_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "second_pass.yaml"

SEVERITY_TABLE = {
    "toc_bleed": {"default": "error", "non_intuitive": "warning"},
    "safety_density_shortfall": {"default": "warning", "intuitive_big": "error"},
    "missing_front_matter": {"default": "warning", "critical": ["manufacturer", "product_name"]},
}

FRONT_MATTER_CRITICAL = set(SEVERITY_TABLE["missing_front_matter"].get("critical", []))

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Issue:
    message: str
    severity: Severity = "error"

    @classmethod
    def error(cls, message: str) -> "Issue":
        return cls(message=message, severity="error")

    @classmethod
    def warn(cls, message: str) -> "Issue":
        return cls(message=message, severity="warning")

    @classmethod
    def info(cls, message: str) -> "Issue":
        return cls(message=message, severity="info")


def _severity_label(kind: str, variant: str = "default") -> str:
    table = SEVERITY_TABLE.get(kind, {})
    candidate = table.get(variant)
    if isinstance(candidate, str):
        return candidate
    fallback = table.get("default")
    if isinstance(fallback, str):
        return fallback
    return "error"


def _issue_from_label(label: str, message: str) -> Issue:
    return Issue.error(message) if label == "error" else Issue.warn(message)


def _front_matter_issue(field: str, *, strict: bool) -> Issue:
    message = f"IFU missing front-matter field '{field}'."
    if strict or field in FRONT_MATTER_CRITICAL:
        return Issue.error(message)
    label = _severity_label("missing_front_matter")
    return _issue_from_label(label, message)


def _coerce_text(value: object) -> Optional[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            stripped = text.strip()
            return stripped or None
    return None


def validate_ifu(document: IFUDocument, config: ExtractionConfig) -> list[Issue]:
    issues: list[Issue] = []
    sync_revision_status(document)

    # Skip validation for non-IFU subtypes
    doc_subtype = getattr(document, "doc_subtype", None)
    skip_clinical = doc_subtype in {"catalog", "installation_guide", "tech_manual"}

    ifu_settings = getattr(config, "ifu", {}) or {}
    small_ifu_threshold = _coerce_positive_int(ifu_settings.get("small_ifu_threshold")) or 4
    page_count = getattr(document, "page_count", 0) or 0
    is_small_ifu = bool(page_count and page_count <= small_ifu_threshold)

    threshold_block = _resolve_threshold_block(config, document.manufacturer)
    strict_front = bool(getattr(threshold_block, "strict_front_matter", False))
    fm_severity = Issue.error if strict_front else Issue.warn

    # Check manufacturer-specific requirements
    manufacturer = document.manufacturer
    manufacturer_overrides = ifu_settings.get("manufacturer_overrides", {})

    mfr_config = {}
    if manufacturer:
        # Check both normalized and raw manufacturer name
        for key, value in manufacturer_overrides.items():
            if key.upper() == manufacturer.upper():
                mfr_config = value if isinstance(value, dict) else {}
                break

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    extracted_chars = _coerce_positive_int(pipeline_info.get("extracted_chars")) if isinstance(pipeline_info, dict) else 0
    page_count = getattr(document, "page_count", 0) or 0
    thresholds = get_safety_thresholds()
    leaflet_pages_max = int(thresholds.get("leaflet_pages_max", 4))  # type: ignore[arg-type]
    is_small_leaflet_doc = bool(page_count and page_count <= leaflet_pages_max)
    revision_status = str(pipeline_info.get("revision_status") or "").strip().lower() if isinstance(pipeline_info, dict) else ""

    # For Intuitive, require cover metadata
    if not manufacturer:
        issues.append(_front_matter_issue("manufacturer", strict=strict_front))

    product_name = getattr(document, "product_name", None)
    if not product_name:
        issues.append(_front_matter_issue("product_name", strict=strict_front))

    if mfr_config.get("require_cover_metadata") and manufacturer and "intuitive" in manufacturer.lower():
        for field in ("part_number", "revision", "model"):
            value = getattr(document, field)
            if not value:
                issues.append(Issue.error(f"Intuitive IFU missing required cover field '{field}'."))
    else:
        # Default validation for other manufacturers
        for field in ("part_number", "revision", "publication_date", "model"):
            value = getattr(document, field)
            if value:
                continue
            if field == "revision" and revision_status == "sanitized_unusable":
                message = "Revision sanitized; original value unusable."
                if is_small_leaflet_doc:
                    issues.append(Issue.info(message))
                else:
                    issues.append(Issue.warn(message))
                continue
            if field == "revision" and extracted_chars and extracted_chars > 100_000:
                if getattr(document, "part_number") and getattr(document, "model"):
                    issues.append(Issue.warn("IFU missing front-matter field 'revision' (large document, tolerated)."))
                    continue
            issues.append(_front_matter_issue(field, strict=strict_front))

    manufacturer_label = (manufacturer or "").strip().lower() if manufacturer else ""
    is_intuitive = "intuitive" in manufacturer_label

    toc_mask: set[int] = set()
    anchor_spans: Dict[str, Dict[str, object]] = {}
    if isinstance(pipeline_info, dict):
        mask_values = pipeline_info.get("toc_guard_pages_dropped") or []
        if isinstance(mask_values, list):
            for value in mask_values:
                try:
                    page_num = int(value)
                except (TypeError, ValueError):
                    continue
                if page_num > 0:
                    toc_mask.add(page_num)
        spans_payload = pipeline_info.get("anchor_spans")
        if isinstance(spans_payload, dict):
            anchor_spans = spans_payload

    if isinstance(pipeline_info, dict):
        anchor_errors = pipeline_info.get("anchor_bleed_errors") or []
        anchor_fields = pipeline_info.get("anchor_bleed_fields") or []
        for idx, message in enumerate(anchor_errors):
            field_name = anchor_fields[idx] if idx < len(anchor_fields) else None
            suffix = f" ({field_name})" if field_name else ""
            if toc_mask and field_name:
                span_dict = anchor_spans.get(field_name) if isinstance(anchor_spans, dict) else None
                if isinstance(span_dict, dict):
                    start_page = _coerce_positive_int(span_dict.get("start_page"))
                    end_page = _coerce_positive_int(span_dict.get("end_page")) or start_page
                    if start_page is not None:
                        start_bound = start_page
                        end_bound = end_page if end_page is not None else start_page
                        if end_bound is None:
                            end_bound = start_bound
                        low = min(start_bound, end_bound)
                        high = max(start_bound, end_bound)
                        span_pages = set(range(low, high + 1))
                        if span_pages.isdisjoint(toc_mask):
                            continue
            severity_variant = "default" if is_intuitive else "non_intuitive"
            bleeds_label = _severity_label("toc_bleed", severity_variant)
            issues.append(_issue_from_label(bleeds_label, f"Clinical anchor bleed detected{suffix}: {message}"))

        dropped = pipeline_info.get("toc_guard_pages_dropped")
        if dropped:
            severity_hint = str(pipeline_info.get("toc_guard_severity") or "warn").lower()
            message = f"TOC guard dropped pages {dropped}"
            if severity_hint == "error":
                issues.append(Issue.error(message))
            else:
                issues.append(Issue.warn(message))

    # Validate required clinical fields for true IFUs
    if doc_subtype != "catalog" and doc_subtype != "installation_guide":
        indications_value = getattr(document, "indications_for_use", None)
        indications_text = _coerce_text(indications_value)
        intended_text = _coerce_text(getattr(document, "intended_use", None))

        if not indications_text:
            if is_small_ifu and intended_text:
                issues.append(Issue.warn("Small IFU missing 'indications_for_use'; intended_use present"))
            else:
                issues.append(Issue.error("IFU missing required field 'indications_for_use'"))
        else:
            indications_clean = ""
            if isinstance(indications_value, str):
                indications_clean = indications_value
            elif isinstance(indications_value, dict):
                literal = indications_value.get("text")
                if isinstance(literal, str):
                    indications_clean = literal
            if indications_clean:
                if any(pattern in indications_clean for pattern in [". . .", "...", "—", "–"]):
                    if len([c for c in indications_clean if c in {'.', '–', '—'}]) > 10:
                        issues.append(Issue.error("Possible TOC bleed detected in indications_for_use"))

    safety_blocks = getattr(document, "safety_blocks", []) or []

    expected_min, threshold_rule = expected_safety_with_source(document)

    found_blocks = len(safety_blocks)
    if isinstance(pipeline_info, dict):
        pipeline_info["safety_expected_min"] = expected_min
        pipeline_info["safety_expected"] = expected_min
        pipeline_info["safety_expectation_source"] = threshold_rule
        pipeline_info["safety_threshold_rule"] = threshold_rule
        pipeline_info["safety_found"] = found_blocks
        pipeline_info["safety_status"] = "ok" if found_blocks >= expected_min else "low"
        pipeline_info["safety_gap"] = max(0, expected_min - found_blocks)

    if isinstance(pipeline_info, dict):
        document.pipeline_info = pipeline_info

    if skip_clinical:
        return issues

    if expected_min > 0:
        tier_hint = None
        if page_count and page_count <= leaflet_pages_max:
            tier_hint = "leaflet (≤4 pages)"
        elif page_count and page_count >= 40:
            tier_hint = "manual (≥40 pages)"
        added_blocks = 0
        if isinstance(pipeline_info, dict):
            try:
                added_blocks = int(pipeline_info.get("safety_blocks_added") or 0)
            except (TypeError, ValueError):
                added_blocks = 0
        parts = [f"Safety blocks {found_blocks}/{expected_min}"]
        if tier_hint:
            parts.append(f"[{tier_hint}]")
        if added_blocks:
            parts.append(f"(+{added_blocks} added)")
        message = " ".join(parts)
        if found_blocks < expected_min:
            issues.append(Issue.warn(message))
        else:
            issues.append(Issue.info(message))

    if getattr(document, "references", None):
        sections_map = {}
        if isinstance(pipeline_info, dict) and isinstance(pipeline_info.get("sections"), dict):
            sections_map = pipeline_info.get("sections") or {}
        elif isinstance(getattr(document, "sections", None), dict):
            sections_map = document.sections  # type: ignore[assignment]
        references_section = sections_map.get("references") if isinstance(sections_map, dict) else None
        has_anchor = False
        if isinstance(references_section, dict):
            if references_section.get("page_span") or references_section.get("start_page"):
                has_anchor = True
        if not has_anchor:
            issues.append(Issue.warn("References detected but references section anchor missing."))
    return issues


def _resolve_threshold_block(
    config: ExtractionConfig,
    manufacturer: Optional[str],
) -> FrozenNamespace:
    thresholds = config.thresholds
    default_block = getattr(thresholds, "default", FrozenNamespace())

    if not manufacturer:
        return default_block

    manufacturer_lower = manufacturer.lower()
    for key, value in thresholds.items():
        if isinstance(value, FrozenNamespace) and key.lower() == manufacturer_lower:
            return value

    normalized = manufacturer_lower.replace(" ", "_")
    candidate = getattr(thresholds, normalized, None)
    if isinstance(candidate, FrozenNamespace):
        return candidate

    return default_block


def _coerce_positive_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


__all__ = ["Issue", "validate_ifu"]
