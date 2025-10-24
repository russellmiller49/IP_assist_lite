"""Manufacturer-specific IFU extraction profiles."""

from __future__ import annotations

import re
from typing import Callable, Dict, List, NamedTuple, Optional


class ManufacturerProfile(NamedTuple):
    """Profile defining manufacturer-specific extraction patterns."""

    name: str
    name_patterns: List[str]  # Patterns to detect this manufacturer
    pn_patterns: List[str]  # Part number patterns
    rev_patterns: List[str]  # Revision patterns
    date_patterns: List[str]  # Date patterns
    model_patterns: List[str]  # Model patterns
    normalize: Callable[[Dict[str, Optional[str]]], Dict[str, Optional[str]]]  # Post-processing


def detect_manufacturer(text: str, profiles: List[ManufacturerProfile]) -> Optional[ManufacturerProfile]:
    """Detect manufacturer from text using profile patterns.

    Args:
        text: Text from first few pages (cover, title page, etc.)
        profiles: List of manufacturer profiles to check

    Returns:
        Matching profile or None
    """
    text_lower = text.lower()
    for profile in profiles:
        for pattern in profile.name_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return profile
    return None


# Import profiles
from .erbe import erbe_profile
from .intuitive import intuitive_profile

# Registry of all profiles
PROFILES = [
    intuitive_profile,
    erbe_profile,
]

__all__ = [
    "ManufacturerProfile",
    "detect_manufacturer",
    "PROFILES",
    "intuitive_profile",
    "erbe_profile",
]
