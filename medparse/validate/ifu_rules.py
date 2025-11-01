"""IFU-specific validation helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Literal, Optional

from medparse.config import ExtractionConfig, FrozenNamespace
from medparse.schema.ifu import IFUDocument

Severity = Literal["error", "warning"]


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

    # Skip validation for non-IFU subtypes
    doc_subtype = getattr(document, "doc_subtype", None)
    if doc_subtype in {"catalog", "installation_guide", "tech_manual"}:
        # Skip clinical field validation for non-IFUs
        return issues

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

    # For Intuitive, require cover metadata
    if mfr_config.get("require_cover_metadata") and manufacturer and "intuitive" in manufacturer.lower():
        for field in ("part_number", "revision", "model"):
            value = getattr(document, field)
            if not value:
                issues.append(Issue.error(f"Intuitive IFU missing required cover field '{field}'."))
    else:
        # Default validation for other manufacturers
        for field in ("part_number", "revision", "publication_date", "model"):
            value = getattr(document, field)
            if not value:
                issues.append(fm_severity(f"IFU missing front-matter field '{field}'."))

    pipeline_info = getattr(document, "pipeline_info", {})
    extracted_chars = _coerce_positive_int(pipeline_info.get("extracted_chars")) if isinstance(pipeline_info, dict) else 0
    if isinstance(pipeline_info, dict):
        anchor_errors = pipeline_info.get("anchor_bleed_errors") or []
        anchor_fields = pipeline_info.get("anchor_bleed_fields") or []
        for idx, message in enumerate(anchor_errors):
            field_name = anchor_fields[idx] if idx < len(anchor_fields) else None
            suffix = f" ({field_name})" if field_name else ""
            issues.append(Issue.error(f"Clinical anchor bleed detected{suffix}: {message}"))

        toc_guard = pipeline_info.get("toc_guard") or {}
        dropped = toc_guard.get("pages_dropped")
        if dropped:
            issues.append(Issue.warn(f"TOC guard dropped pages {dropped}"))

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
    page_count = getattr(document, "page_count", 0) or 0

    safety_config: Dict[str, object] = {}
    try:
        safety_ns = config.ifu_settings.get("safety")
    except AttributeError:
        safety_ns = None
    if safety_ns is None:
        raw_safety = getattr(config, "ifu", {}).get("safety") if isinstance(getattr(config, "ifu", {}), dict) else {}
        safety_config = raw_safety or {}
    else:
        if hasattr(safety_ns, "to_dict"):
            safety_config = safety_ns.to_dict()
        elif isinstance(safety_ns, dict):
            safety_config = safety_ns

    default_safety = safety_config.get("default", {}) if isinstance(safety_config, dict) else {}
    manufacturer_rules = {}
    manufacturer_normalized = (document.manufacturer or "").strip().upper()
    overrides = safety_config.get("manufacturers") if isinstance(safety_config, dict) else {}
    if manufacturer_normalized and isinstance(overrides, dict):
        for key, value in overrides.items():
            if key.strip().upper() == manufacturer_normalized and isinstance(value, dict):
                manufacturer_rules = value
                break

    def _resolve_threshold(name: str, default_value: int) -> int:
        candidate = manufacturer_rules.get(name)
        if candidate is None:
            candidate = default_safety.get(name, default_value)
        try:
            return int(candidate)
        except (TypeError, ValueError):
            return default_value

    small_max_pages = _resolve_threshold("small_max_pages", 6)
    small_min_blocks = _resolve_threshold("small_min_blocks", 0)
    min_blocks_standard = _resolve_threshold("min_blocks", 4)
    large_page_threshold = _resolve_threshold("large_page_threshold", 80)
    large_min_blocks = _resolve_threshold("large_min_blocks", 20)
    chars_per_block = _resolve_threshold("chars_per_block", 7500)

    expected_density = min_blocks_standard
    if page_count and page_count <= small_max_pages:
        expected_density = small_min_blocks
    else:
        if extracted_chars and chars_per_block > 0:
            char_based = math.ceil(extracted_chars / chars_per_block)
            expected_density = max(expected_density, min(large_min_blocks, char_based))
        if page_count and page_count >= large_page_threshold:
            expected_density = max(expected_density, large_min_blocks)

    if expected_density > 0 and len(safety_blocks) < expected_density:
        severity_fn = Issue.warn if (page_count and page_count <= small_max_pages) else Issue.error
        issues.append(
            severity_fn(
                f"Safety content below expected density (found {len(safety_blocks)}, expected >= {expected_density})"
            )
        )

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
