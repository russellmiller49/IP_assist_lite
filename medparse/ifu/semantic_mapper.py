"""Semantic field mapping for IFU fields with alternative headings."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

# Semantic mappings for IFU clinical fields
# Maps alternative headings to canonical field names

SEMANTIC_FIELD_MAPPINGS: Dict[str, Set[str]] = {
    "indications_for_use": {
        "indications for use",
        "indications",
        "indication",
        "intended use",
        "device description and indication",
        "device description and indications",
        "description and indication",
        "clinical indication",
        "clinical indications",
    },
    "contraindications": {
        "contraindications",
        "contraindication",
        "when not to use",
        "when not to use the device",
        "restrictions",
    },
    "adverse_events": {
        "adverse events",
        "adverse reactions",
        "adverse effects",
        "side effects",
        "complications",
        "potential complications",
        "risks",
        "clinical risks",
        "clinical risks and benefits",  # Common alternative
        "risks and benefits",
        "safety information",
        "hazards",
    },
    "warnings": {
        "warnings",
        "warning",
        "important warnings",
        "safety warnings",
        "caution",
        "cautions",
        "precautions",
        "important precautions",
    },
    "intended_user": {
        "intended user",
        "intended users",
        "intended audience",
        "target users",
        "qualified users",
        "user qualifications",
        "practitioner qualifications",
    },
    "intended_patient_population": {
        "intended patient population",
        "patient population",
        "target population",
        "patient selection",
        "patient criteria",
    },
}

# Compile patterns for fuzzy matching
FUZZY_PATTERNS: Dict[str, List[re.Pattern]] = {}
for field, aliases in SEMANTIC_FIELD_MAPPINGS.items():
    patterns = []
    for alias in aliases:
        # Create pattern that allows for minor variations
        # e.g., "adverse events" matches "adverse event", "adverse-events", etc.
        escaped = re.escape(alias)
        # Allow s/no-s variations
        pattern_str = escaped.replace(r"\ ", r"[\s\-_]*").rstrip("s") + "s?"
        patterns.append(re.compile(pattern_str, re.IGNORECASE))
    FUZZY_PATTERNS[field] = patterns


def find_semantic_field_match(section_title: str) -> Optional[str]:
    """Find canonical field name for a given section title.

    Args:
        section_title: Section heading from document (e.g., "Clinical Risks and Benefits")

    Returns:
        Canonical field name (e.g., "adverse_events") or None if no match
    """
    if not section_title:
        return None

    normalized = section_title.strip().lower()

    # First: exact match
    for field, aliases in SEMANTIC_FIELD_MAPPINGS.items():
        if normalized in aliases:
            return field

    # Second: fuzzy match
    for field, patterns in FUZZY_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(normalized):
                return field

    return None


def map_extracted_sections(
    raw_sections: Dict[str, str],
    *,
    prefer_explicit: bool = True,
) -> Dict[str, str]:
    """Map raw extracted sections to canonical field names.

    Args:
        raw_sections: Dictionary mapping section titles to content
        prefer_explicit: If True, don't override explicitly extracted fields

    Returns:
        Dictionary with canonical field names
    """
    canonical_sections: Dict[str, str] = {}

    # First pass: copy over fields that are already canonical
    for title, content in raw_sections.items():
        normalized_title = title.strip().lower().replace(" ", "_")
        if normalized_title in SEMANTIC_FIELD_MAPPINGS:
            canonical_sections[normalized_title] = content

    # Second pass: map non-canonical titles
    for title, content in raw_sections.items():
        normalized_title = title.strip().lower().replace(" ", "_")

        # Skip if already mapped
        if normalized_title in canonical_sections:
            continue

        # Try semantic mapping
        canonical_field = find_semantic_field_match(title)

        if canonical_field:
            # Only override if field is empty or prefer_explicit is False
            if not prefer_explicit or canonical_field not in canonical_sections:
                canonical_sections[canonical_field] = content

    return canonical_sections


def get_field_aliases(field_name: str) -> List[str]:
    """Get all known aliases for a canonical field name.

    Args:
        field_name: Canonical field name (e.g., "adverse_events")

    Returns:
        List of alternative headings
    """
    if field_name in SEMANTIC_FIELD_MAPPINGS:
        return sorted(SEMANTIC_FIELD_MAPPINGS[field_name])
    return []


def extend_field_anchors(
    field_name: str,
    existing_anchors: List[str],
) -> List[str]:
    """Extend field anchors with semantic aliases.

    Args:
        field_name: Canonical field name
        existing_anchors: Current anchor list

    Returns:
        Extended anchor list including semantic alternatives
    """
    if field_name not in SEMANTIC_FIELD_MAPPINGS:
        return existing_anchors

    # Get all aliases
    aliases = SEMANTIC_FIELD_MAPPINGS[field_name]

    # Combine and deduplicate
    extended = list(existing_anchors)
    for alias in aliases:
        if alias not in extended:
            extended.append(alias)

    return extended


__all__ = [
    "SEMANTIC_FIELD_MAPPINGS",
    "find_semantic_field_match",
    "map_extracted_sections",
    "get_field_aliases",
    "extend_field_anchors",
]
