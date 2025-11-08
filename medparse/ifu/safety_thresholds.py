"""Shared helpers for IFU safety-density expectations."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Dict, Tuple

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "second_pass.yaml"


def _coerce_positive_int(value: object, default: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


@functools.lru_cache(maxsize=1)
def _load_threshold_config() -> Dict[str, object]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if isinstance(data, dict):
        data = data.get("second_pass", data)
    if not isinstance(data, dict):
        return {}
    ifu_block = data.get("ifu")
    if not isinstance(ifu_block, dict):
        return {}

    safety_block = ifu_block.get("safety")
    if not isinstance(safety_block, dict):
        safety_block = {}

    # Backward compatibility: merge legacy safety_density_min overrides.
    legacy_block = ifu_block.get("safety_density_min")
    if isinstance(legacy_block, dict):
        safety_block = {**legacy_block, **safety_block}

    return safety_block


def get_safety_thresholds() -> Dict[str, int | Dict[str, int]]:
    """Return sanitized safety-threshold settings."""

    raw_cfg = _load_threshold_config()
    thresholds: Dict[str, int | Dict[str, int]] = {}
    thresholds["min_short"] = _coerce_positive_int(raw_cfg.get("min_short"), 8)
    thresholds["leaflet_pages_max"] = _coerce_positive_int(raw_cfg.get("leaflet_pages_max"), 4)
    thresholds["cap_long"] = _coerce_positive_int(raw_cfg.get("cap_long"), 20)
    thresholds["chars_per_10"] = _coerce_positive_int(raw_cfg.get("chars_per_10"), 50_000)

    legacy_small = raw_cfg.get("small_leaflet")
    if legacy_small and not raw_cfg.get("min_short"):
        thresholds["min_short"] = _coerce_positive_int(legacy_small, thresholds["min_short"])  # type: ignore[index]

    legacy_leaf_max = raw_cfg.get("small_leaflet_pages_max")
    if legacy_leaf_max and not raw_cfg.get("leaflet_pages_max"):
        thresholds["leaflet_pages_max"] = _coerce_positive_int(legacy_leaf_max, thresholds["leaflet_pages_max"])  # type: ignore[index]

    if isinstance(raw_cfg.get("by_manufacturer"), dict):
        thresholds["by_manufacturer"] = {
            key: _coerce_positive_int(value, thresholds["min_short"])  # type: ignore[index]
            for key, value in raw_cfg["by_manufacturer"].items()
            if isinstance(key, str)
        }
    else:
        thresholds["by_manufacturer"] = {}

    return thresholds


def _match_manufacturer_threshold(
    manufacturer: str | None,
    overrides: Dict[str, int],
) -> tuple[int | None, str | None]:
    if not manufacturer or not overrides:
        return None, None
    normalized = manufacturer.lower()
    for name, value in overrides.items():
        if not isinstance(name, str):
            continue
        alias = name.strip().lower()
        if alias and alias in normalized:
            return value, alias
    return None, None


def expected_safety_with_source(
    char_count: int,
    page_count: int,
    manufacturer: str | None = None,
) -> Tuple[int, str]:
    """Return (expected_blocks, source_label) for IFU safety expectations."""

    thresholds = get_safety_thresholds()
    min_short = thresholds.get("min_short", 8)  # type: ignore[assignment]
    leaflet_pages_max = thresholds.get("leaflet_pages_max", 4)  # type: ignore[assignment]
    cap_long = thresholds.get("cap_long", 20)  # type: ignore[assignment]
    chars_per_10 = thresholds.get("chars_per_10", 50_000)  # type: ignore[assignment]
    overrides = thresholds.get("by_manufacturer", {})  # type: ignore[assignment]

    if page_count > 0 and page_count <= leaflet_pages_max:
        return int(min_short), "leaflet"

    vendor_expected, vendor_label = _match_manufacturer_threshold(manufacturer, overrides if isinstance(overrides, dict) else {})
    if vendor_expected:
        return vendor_expected, f"manufacturer:{vendor_label or 'override'}"

    if char_count <= 0 or chars_per_10 <= 0:
        base = min_short
    else:
        base = round(char_count / chars_per_10) * 10

    if base <= 0:
        base = min_short

    expected = max(min_short, min(cap_long, base))
    return int(expected), "dynamic"


def expected_safety_min(
    char_count: int,
    page_count: int,
    manufacturer: str | None = None,
) -> int:
    """Return the minimum expected safety blocks for the given document."""

    expected, _ = expected_safety_with_source(char_count, page_count, manufacturer)
    return expected


__all__ = ["expected_safety_min", "expected_safety_with_source", "get_safety_thresholds"]
