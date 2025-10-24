"""Intuitive Surgical manufacturer profile."""

from __future__ import annotations

import re
from typing import Dict, Optional


def normalize_intuitive_front_matter(data: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """Normalize front-matter for Intuitive Surgical IFUs.

    Args:
        data: Raw extracted fields

    Returns:
        Normalized fields
    """
    normalized = data.copy()

    # Part number: remove trailing REV/Rev suffixes
    if normalized.get("part_number"):
        pn = normalized["part_number"]
        pn = re.sub(r'\s*REV.*$', '', pn, flags=re.IGNORECASE)
        normalized["part_number"] = pn.strip()

    # Revision: canonicalize to "Rev X" format
    if normalized.get("revision"):
        rev = normalized["revision"]
        # Ensure "Rev " prefix
        if not rev.startswith("Rev "):
            normalized["revision"] = f"Rev {rev}"

    # Publication date: ensure YYYY-MM-DD format
    if normalized.get("publication_date"):
        date = normalized["publication_date"]
        # Should already be normalized by extract function
        # Ensure it has day component (default to -01)
        if re.match(r'^\d{4}-\d{2}$', date):
            normalized["publication_date"] = f"{date}-01"

    # Model: uppercase, remove spaces
    if normalized.get("model"):
        model = normalized["model"]
        normalized["model"] = model.upper().replace(' ', '')

    # Manufacturer: canonical form
    if normalized.get("manufacturer"):
        normalized["manufacturer"] = "Intuitive Surgical, Inc."

    return normalized


# Intuitive Surgical profile
intuitive_profile = None  # Will be created after import to avoid circular dependency


def _create_profile():
    """Create Intuitive profile (called after imports)."""
    from medparse.manufacturers import ManufacturerProfile

    return ManufacturerProfile(
        name="Intuitive Surgical",
        name_patterns=[
            r"\bIntuitive\s+Surgical",
            r"\bIntuitive\s+Surgical,?\s+Inc",
        ],
        pn_patterns=[
            r'\b(5\d{5}-\d{2})\b',  # 553990-11 format
        ],
        rev_patterns=[
            r'\bRev(?:ision)?\s*\.?\s*([A-Z]\d?)\b',  # Rev C, Rev. C, Revision C
        ],
        date_patterns=[
            r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
            r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b',
            r'\b\d{4}\s*[.\-]\s*\d{2}\b',  # 2024-08, 2024.08, 2024 . 08
        ],
        model_patterns=[
            r'\bModel\s+([A-Z]{1,3}\s?\d{3,4})\b',  # Model IF1000, Model IF 1000
        ],
        normalize=normalize_intuitive_front_matter,
    )


# Create profile at module load
intuitive_profile = _create_profile()

__all__ = ["intuitive_profile", "normalize_intuitive_front_matter"]
