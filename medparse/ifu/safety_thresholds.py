"""Shared helpers for IFU safety-density expectations."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml

POLICY_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "ifu_policy.yaml"
LEGACY_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "second_pass.yaml"


@dataclass(frozen=True)
class SafetyExpectation:
    minimum: int
    rule: str


def _coerce_positive_int(value: object, default: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _coerce_int(value: object) -> Optional[int]:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_legacy_policy() -> Dict[str, Any]:
    """Load historic safety-density thresholds from second_pass.yaml."""

    config_data = _read_yaml(LEGACY_PATH)
    if not config_data:
        return {}
    block = config_data.get("second_pass", config_data)
    if not isinstance(block, dict):
        return {}
    ifu_block = block.get("ifu")
    if not isinstance(ifu_block, dict):
        return {}

    density_block = ifu_block.get("safety_density_min")
    if not isinstance(density_block, dict):
        density_block = {}
    safety_block = ifu_block.get("safety")
    if not isinstance(safety_block, dict):
        safety_block = {}

    default_min = density_block.get("default")
    if default_min is None:
        default_min = safety_block.get("cap_long")
    default_min_blocks = _coerce_positive_int(default_min, 12)

    short_max_pages = _coerce_positive_int(
        density_block.get("short_max_pages") or safety_block.get("leaflet_pages_max"),
        4,
    )
    short_min_blocks = _coerce_positive_int(
        density_block.get("short_min_blocks") or safety_block.get("min_short"),
        8,
    )
    long_min_pages = _coerce_positive_int(
        density_block.get("long_min_pages") or safety_block.get("long_manual_pages_min"),
        40,
    )
    long_min_blocks = _coerce_positive_int(
        density_block.get("long_min_blocks") or safety_block.get("cap_long"),
        20,
    )

    small_leaflet = {
        "max_pages": _coerce_positive_int(
            density_block.get("small_leaflet_pages_max") or safety_block.get("leaflet_pages_max"),
            4,
        ),
        "min_blocks": _coerce_positive_int(
            density_block.get("small_leaflet") or safety_block.get("min_short"),
            8,
        ),
        "subtype_labels": ["small_leaflet"],
    }

    overrides_source = density_block.get("by_manufacturer") or safety_block.get("by_manufacturer") or {}
    manufacturer_overrides = []
    if isinstance(overrides_source, dict):
        for name, value in overrides_source.items():
            if not isinstance(name, str):
                continue
            manufacturer_overrides.append(
                {
                    "manufacturer": name,
                    "min_blocks": _coerce_positive_int(value, default_min_blocks),
                }
            )

    return {
        "default_min_blocks": default_min_blocks,
        "small_leaflet": small_leaflet,
        "short_max_pages": short_max_pages,
        "short_min_blocks": short_min_blocks,
        "long_min_pages": long_min_pages,
        "long_min_blocks": long_min_blocks,
        "manufacturer_overrides": manufacturer_overrides,
    }


def _load_explicit_policy() -> Dict[str, Any]:
    policy_data = _read_yaml(POLICY_PATH)
    if not policy_data:
        return {}
    density = policy_data.get("safety_density")
    return density if isinstance(density, dict) else {}


@functools.lru_cache(maxsize=1)
def _load_policy() -> Dict[str, Any]:
    """Load safety-density policy, preferring explicit config over legacy defaults."""

    policy = _load_legacy_policy()
    explicit = _load_explicit_policy()
    if not explicit:
        return policy

    merged = dict(policy)
    for key, value in explicit.items():
        if key == "manufacturer_overrides" and isinstance(value, list):
            merged[key] = list(value)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            existing = dict(merged[key])
            existing.update(value)
            merged[key] = existing
        else:
            merged[key] = value
    return merged


def _get_attr(document: object, attr: str) -> Any:
    if document is None:
        return None
    if isinstance(document, Mapping):
        if attr in document:
            return document[attr]
    return getattr(document, attr, None)


def _resolve_title(document: object) -> str:
    for attr in ("product_name", "title", "document_title"):
        value = _get_attr(document, attr)
        if isinstance(value, str) and value.strip():
            return value.strip()
    pipeline_info = getattr(document, "pipeline_info", None)
    if isinstance(pipeline_info, dict):
        for key in ("product_name", "metadata_title", "pdf_basename"):
            value = pipeline_info.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    source_name = _get_attr(document, "source_file")
    if isinstance(source_name, str) and source_name:
        return Path(source_name).stem.replace("_", " ").strip()
    return ""


def _apply_small_leaflet_rule(policy: Dict[str, Any], document: object) -> Optional[SafetyExpectation]:
    small_leaflet = policy.get("small_leaflet")
    if not isinstance(small_leaflet, dict):
        return None
    min_blocks = _coerce_positive_int(small_leaflet.get("min_blocks"), 8)
    max_pages = _coerce_positive_int(small_leaflet.get("max_pages"), 4)
    page_count = max(0, _to_int(_get_attr(document, "page_count")))
    if max_pages and page_count and page_count <= max_pages:
        return SafetyExpectation(minimum=min_blocks, rule="small_leaflet")

    subtype_labels = {
        str(label).strip().lower()
        for label in small_leaflet.get("subtype_labels", [])
        if isinstance(label, str) and label.strip()
    }
    doc_subtype = str((_get_attr(document, "doc_subtype") or "")).strip().lower()
    if subtype_labels and doc_subtype in subtype_labels:
        return SafetyExpectation(minimum=min_blocks, rule="small_leaflet")
    pipeline_info = getattr(document, "pipeline_info", None)
    if isinstance(pipeline_info, dict):
        for key in ("doc_subtype", "ifu_subtype"):
            candidate = pipeline_info.get(key)
            if isinstance(candidate, str) and candidate.strip().lower() in subtype_labels:
                return SafetyExpectation(minimum=min_blocks, rule="small_leaflet")
    return None


def _manufacturer_matches(needle: str, haystack: str) -> bool:
    normalized = needle.strip().lower()
    if not normalized:
        return False
    lowered = haystack.strip().lower()
    return normalized in lowered if lowered else False


def _apply_manufacturer_overrides(
    policy: Dict[str, Any],
    document: object,
    default_min: int,
) -> Optional[SafetyExpectation]:
    overrides = policy.get("manufacturer_overrides")
    if not isinstance(overrides, list):
        return None
    manufacturer_value = str(_get_attr(document, "manufacturer") or "").strip().lower()
    if not manufacturer_value:
        pipeline_info = getattr(document, "pipeline_info", None)
        if isinstance(pipeline_info, dict):
            extra = pipeline_info.get("manufacturer")
            if isinstance(extra, str):
                manufacturer_value = extra.strip().lower()
    page_count = max(0, _to_int(_get_attr(document, "page_count")))
    title_value = _resolve_title(document).lower()

    for override in overrides:
        if not isinstance(override, dict):
            continue
        names = override.get("manufacturer")
        name_matches = False
        if isinstance(names, str):
            name_matches = _manufacturer_matches(names, manufacturer_value)
        elif isinstance(names, list):
            name_matches = any(
                isinstance(candidate, str) and _manufacturer_matches(candidate, manufacturer_value)
                for candidate in names
            )
        if not name_matches:
            continue
        min_pages = _coerce_int(override.get("min_pages"))
        if min_pages is not None and page_count and page_count < min_pages:
            continue
        max_pages = _coerce_int(override.get("max_pages"))
        if max_pages is not None and page_count and page_count > max_pages:
            continue
        title_terms = override.get("title_contains")
        if isinstance(title_terms, str):
            title_terms = [title_terms]
        if isinstance(title_terms, list) and title_terms:
            if not any(isinstance(term, str) and term.lower() in title_value for term in title_terms):
                continue
        min_blocks = _coerce_positive_int(override.get("min_blocks"), default_min)
        rule_label = str(override.get("rule") or "manufacturer_override")
        return SafetyExpectation(minimum=min_blocks, rule=rule_label)

    return None


def _resolve_expectation(document: object) -> SafetyExpectation:
    policy = _load_policy()
    short_max_pages = _coerce_positive_int(policy.get("short_max_pages"), 4)
    short_min_blocks = _coerce_positive_int(policy.get("short_min_blocks"), 8)
    long_min_pages = _coerce_positive_int(policy.get("long_min_pages"), 40)
    long_min_blocks = _coerce_positive_int(policy.get("long_min_blocks"), 20)
    default_min = _coerce_positive_int(policy.get("default_min_blocks"), 12)

    small_leaflet = _apply_small_leaflet_rule(policy, document)
    if small_leaflet:
        expectation = small_leaflet
    else:
        page_count = max(0, _to_int(_get_attr(document, "page_count")))
        if short_max_pages and page_count and page_count <= short_max_pages:
            expectation = SafetyExpectation(minimum=short_min_blocks, rule="short_doc")
        elif long_min_pages and page_count and page_count >= long_min_pages:
            expectation = SafetyExpectation(minimum=long_min_blocks, rule="long_doc")
        else:
            expectation = SafetyExpectation(minimum=default_min, rule="default")

    override = _apply_manufacturer_overrides(policy, document, expectation.minimum)
    if override:
        return override
    return expectation


def expected_safety_with_source(document: object | None) -> Tuple[int, str]:
    """Return (expected_blocks, rule_label) for IFU safety expectations."""

    expectation = _resolve_expectation(document)
    return expectation.minimum, expectation.rule


def expected_safety_min(document: object | None) -> int:
    """Return the minimum expected safety blocks for the given document."""

    expected, _ = expected_safety_with_source(document)
    return expected


def get_safety_thresholds() -> Dict[str, int]:
    """Expose basic leaflet thresholds for downstream helpers."""

    policy = _load_policy()
    small_leaflet = policy.get("small_leaflet") if isinstance(policy.get("small_leaflet"), dict) else {}
    return {
        "min_short": _coerce_positive_int(small_leaflet.get("min_blocks"), 8),
        "leaflet_pages_max": _coerce_positive_int(small_leaflet.get("max_pages"), 4),
    }


__all__ = ["expected_safety_min", "expected_safety_with_source", "get_safety_thresholds"]
