"""ERBE Elektromedizin manufacturer profile."""

from __future__ import annotations

import re
from typing import Dict, Optional


def normalize_erbe_front_matter(data: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """Normalize front-matter for ERBE IFUs.

    ERBE uses formats like:
    - Part: "30180-103" or "Art.-Nr. 20180-110"
    - Version: "V 25709" (version number, not letter revision)
    - Date: "2025-01" (YYYY-MM) or "31.12.2024" (DD.MM.YYYY)
    - Model: Often embedded in product name like "AUTOCON II", "VIO 3"

    Args:
        data: Raw extracted fields

    Returns:
        Normalized fields
    """
    normalized = data.copy()

    # Part number: clean Art.-Nr. prefix
    if normalized.get("part_number"):
        pn = normalized["part_number"]
        pn = re.sub(r'(?i)Art\.?\s*-?\s*Nr\.?\s*[:#]?\s*', '', pn)
        normalized["part_number"] = pn.strip()

    # Revision: ERBE uses "V NNNNN" version numbers
    if normalized.get("revision"):
        rev = normalized["revision"]
        # Canonicalize to "V NNNNN" format
        m = re.match(r'(?i)V\s*(\d+)', rev)
        if m:
            normalized["revision"] = f"V {m.group(1)}"

    # Publication date: normalize DD.MM.YYYY or YYYY-MM to YYYY-MM-DD
    if normalized.get("publication_date"):
        date = normalized["publication_date"]

        # Handle DD.MM.YYYY format
        m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', date)
        if m:
            day, month, year = m.groups()
            normalized["publication_date"] = f"{year}-{month}-{day}"
        # Handle YYYY-MM format (pad with -01)
        elif re.match(r'^\d{4}-\d{2}$', date):
            normalized["publication_date"] = f"{date}-01"

    # Model: uppercase common ERBE product names
    if normalized.get("model"):
        model = normalized["model"]
        normalized["model"] = model.upper()

    # Manufacturer: canonical form
    if normalized.get("manufacturer"):
        normalized["manufacturer"] = "ERBE Elektromedizin GmbH"

    return normalized


# ERBE profile
erbe_profile = None  # Will be created after import


def _create_profile():
    """Create ERBE profile (called after imports)."""
    from medparse.manufacturers import ManufacturerProfile

    return ManufacturerProfile(
        name="ERBE",
        name_patterns=[
            r"\bERBE\b",
            r"ERBE\s+Elektromedizin",
            r"Erbe\s+Elektromedizin",
        ],
        pn_patterns=[
            r'\b(\d{5}-\d{3})\b',  # 30180-103, 85100-172
            r'Art\.?\s*-?\s*Nr\.?\s*[:#]?\s*(\d{5}-\d{3})',  # Art.-Nr. 20180-110
            r'Art\.?\s*No\.?\s*[:#]?\s*(\d{5}-\d{3})',
        ],
        rev_patterns=[
            r'\bRev\.?\s*([A-Z0-9]+)\b',  # Rev. C (if present)
            r'\b(V\s*\d{3,6})\b',  # V 25709, V25709
        ],
        date_patterns=[
            r'\b(\d{4})-(\d{2})\b',  # 2025-01
            r'\b(\d{2})\.(\d{2})\.(\d{4})\b',  # 31.12.2024
            r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
            r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b',
        ],
        model_patterns=[
            r'\b(AUTOCON)\s*(?:II|III|[0-9]+)?\b',  # AUTOCON II
            r'\b(VIO)\s*(?:[0-9]+)?\b',  # VIO 3
            r'\b(APC)\s*(?:[0-9]+)?\b',  # APC
            r'\b(UNIT|MODULE|SYSTEM)\s+\w+\b',  # System Carrier
            r'Art\.?\s*No\.?\s*[:#]?\s*(\d{5}-\d{3})',  # Use Art. No. as fallback
        ],
        normalize=normalize_erbe_front_matter,
    )


# Create profile at module load
erbe_profile = _create_profile()

__all__ = ["erbe_profile", "normalize_erbe_front_matter"]
