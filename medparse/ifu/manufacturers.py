"""Manufacturer-specific heuristics for IFU anchor selection."""

from __future__ import annotations

from typing import Dict, Optional

MANUFACTURER_RULES: Dict[str, Dict[str, object]] = {
    "INTUITIVE SURGICAL, INC.": {
        "min_anchor_page": 10,
    },
    "INTUITIVE SURGICAL": {
        "min_anchor_page": 10,
    },
    "ION": {
        "min_anchor_page": 10,
    },
    "ION ENDOLUMINAL SYSTEM": {
        "min_anchor_page": 10,
    },
}


def get_manufacturer_rules(name: Optional[str]) -> Dict[str, object]:
    if not name:
        return {}
    normalized = name.strip().upper()
    return MANUFACTURER_RULES.get(normalized, {}).copy()


__all__ = ["get_manufacturer_rules", "MANUFACTURER_RULES"]
