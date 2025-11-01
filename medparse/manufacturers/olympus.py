"""Olympus manufacturer profile."""

from __future__ import annotations

import re
from typing import Dict, Optional


def normalize_olympus_front_matter(data: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """Normalize Olympus front-matter fields."""

    normalized = data.copy()
    normalized["manufacturer"] = "Olympus Corporation"

    product = normalized.get("product_name")
    if product and "olympus" not in product.lower():
        normalized["product_name"] = f"Olympus {product}"

    revision = normalized.get("revision")
    if revision:
        match = re.match(r"rev\s*([A-Z0-9]+)", revision, flags=re.IGNORECASE)
        if match:
            normalized["revision"] = f"Rev {match.group(1)}"

    return normalized


def _create_profile():
    from medparse.manufacturers import ManufacturerProfile

    return ManufacturerProfile(
        name="Olympus",
        name_patterns=[
            r"\bOlympus\b",
            r"\bOlympus\s+Corporation\b",
        ],
        pn_patterns=[
            r"\b(ALT-?Pro)\b",
            r"\b([A-Z]{2,}\d{2,}-\d{2,})\b",
        ],
        rev_patterns=[
            r"\bRev\.?\s*([A-Z0-9]+)\b",
        ],
        date_patterns=[
            r"\b\d{4}\b",
            r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b",
        ],
        model_patterns=[
            r"\bALT-?Pro\b",
            r"\bSystemCarrier\b",
        ],
        normalize=normalize_olympus_front_matter,
    )


olympus_profile = _create_profile()

__all__ = ["olympus_profile", "normalize_olympus_front_matter"]

