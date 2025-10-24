"""Filter product software versions from IFU text snippets."""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

from medparse.normalize.pre_normalize import pre_normalize

# Robust allowlist patterns (work post-normalization)
# Tolerate 0-1 spaces, accept v/version/V, allow 2-4 version components
ION_OS = re.compile(r'''
    \bIon\s*OS                 # Ion OS / IonOS (handled by pre_normalize)
    \s*(?:v|version)?\s*
    (?P<ver>\d+(?:\.\d+){1,3}) # 2-4 components: 6.0 or 6.0.0 or 6.0.0.1
    (?:\s*(?:and|or)?\s*later)?\b
''', re.IGNORECASE | re.VERBOSE)

PLANPOINT_OS = re.compile(r'''
    \bPlan\s*Point
    (?:\s*(?:Software|OS))?    # Plan Point, Plan Point Software, Plan Point OS
    \s*(?:v|version)?\s*
    (?P<ver>\d+(?:\.\d+){1,3})
    (?:\s*(?:and|or)?\s*later)?\b
''', re.IGNORECASE | re.VERBOSE)

# Denylist patterns: licenses, third-party libs, generic servers
DENY_PATTERNS = [
    re.compile(r'\bFFmpeg\b', re.IGNORECASE),
    re.compile(r'\bLGPL\b', re.IGNORECASE),
    re.compile(r'\bGPL\b', re.IGNORECASE),
    re.compile(r'\bOpenSSL\b', re.IGNORECASE),
    re.compile(r'\blicen[cs]e\b', re.IGNORECASE),
    re.compile(r'\bthird[- ]party\b', re.IGNORECASE),
    re.compile(r'\bpackage\b', re.IGNORECASE),
    re.compile(r'\blibrary\b', re.IGNORECASE),
]


def _cleanup_inline(text: str) -> str:
    """Cleanup inline text (collapse whitespace)."""
    return re.sub(r'\s+', ' ', text).strip()


def _normalize_sw_line(text: str) -> str:
    """Pre-normalize software line before pattern matching.

    Inserts spaces for concatenations and fixes common issues.

    Args:
        text: Raw software line

    Returns:
        Normalized line
    """
    # Insert spaces for concatenated product names
    text = re.sub(r'(Ion)(OS)', r'\1 OS', text, flags=re.IGNORECASE)  # IonOS → Ion OS
    text = re.sub(r'(PlanPoint)(OS)', r'\1 OS', text, flags=re.IGNORECASE)  # PlanPointOS → PlanPoint OS
    text = re.sub(r'(PlanPoint)(Software)', r'\1 Software', text, flags=re.IGNORECASE)  # PlanPointSoftware → PlanPoint Software

    # Normalize version prefix: V/v → v
    text = re.sub(r'\b[Vv]\s+(\d)', r'v\1', text)  # V 4.0 → v4.0

    # Fix spaced version numbers: "6. 0. 0" → "6.0.0" (iterative)
    for _ in range(5):  # Handle up to 5 version components
        new_text = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', text)
        if new_text == text:
            break
        text = new_text

    # Collapse multiple spaces
    text = re.sub(r'\s{2,}', ' ', text).strip()

    return text


def _normalize_version(text: str) -> str:
    """Normalize software version string to canonical format.

    Fixes spacing artifacts and standardizes output:
        - "Ion OS 1 v 6. 0. 0" → "Ion OS v6.0.0"
        - "PlanPoint Software v 4. 0" → "PlanPoint OS v4.0"

    Args:
        text: Normalized software line

    Returns:
        Canonical version string
    """
    # Remove extra digits before 'v': "Ion OS 1 v 6.0.0" → "Ion OS v6.0.0"
    text = re.sub(r'\b(\d+)\s+v\s*', r'v', text, flags=re.IGNORECASE)

    # Ensure 'v' directly before version number: "v 6.0.0" → "v6.0.0"
    text = re.sub(r'[Vv]\s+(\d)', r'v\1', text)

    # Canonicalize "PlanPoint Software" → "PlanPoint OS"
    text = re.sub(r'\bPlanPoint\s+Software\b', 'PlanPoint OS', text, flags=re.IGNORECASE)

    # Ensure consistent casing: "ion os" → "Ion OS"
    text = re.sub(r'\bion\s+os\b', 'Ion OS', text, flags=re.IGNORECASE)
    text = re.sub(r'\bplanpoint\s+os\b', 'PlanPoint OS', text, flags=re.IGNORECASE)

    # Collapse spaces
    text = re.sub(r'\s{2,}', ' ', text)

    return text.strip()


def canonicalize_version(ver: str, pad_to: int = 3) -> str:
    """Canonicalize version string to N.N.N format.

    Args:
        ver: Version string like "6.0" or "6.0.0.1"
        pad_to: Number of components to pad to (default 3)

    Returns:
        Canonical version like "6.0.0"
    """
    parts = [int(p) for p in ver.split('.')]
    while len(parts) < pad_to:
        parts.append(0)
    return '.'.join(str(p) for p in parts[:pad_to])


def _dedupe(items: List[str]) -> List[str]:
    """Deduplicate while preserving order."""
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def filter_software_versions(raw: Iterable[str] | None) -> List[str]:
    """Keep only Ion/Plan Point OS lines; drop FFmpeg/LGPL/generic items.

    Three-stage filtering:
    1. Pre-normalize: Fix concatenations and spacing (uses global pre_normalize)
    2. Loose harvest: Check for product names
    3. Strict filter: Drop noise lines, apply allowlist patterns

    Normalizes version strings to canonical format (e.g., "Ion OS v6.0.0").

    Args:
        raw: Iterable of candidate strings (from software_versions field)

    Returns:
        List of filtered and normalized strings like "Ion OS v6.0.0", "Plan Point OS v4.0"
    """
    if not raw:
        return []

    keep: List[str] = []

    for entry in raw:
        if not isinstance(entry, str):
            continue

        # Stage 1: Pre-normalize the line (global normalizer)
        entry_norm = pre_normalize(entry)
        entry_lower = entry_norm.lower()

        # Stage 2: Loose harvest - check for product names
        has_ion = "ion" in entry_lower and "os" in entry_lower
        has_planpoint = "plan" in entry_lower and "point" in entry_lower

        if not (has_ion or has_planpoint):
            continue

        # Stage 3: Strict filter - drop noise unless legitimate version line
        is_noise = any(pattern.search(entry_norm) for pattern in DENY_PATTERNS)

        if is_noise:
            # Only keep if allowlist patterns match
            if not (ION_OS.search(entry_norm) or PLANPOINT_OS.search(entry_norm)):
                continue

        # Keep and canonicalize
        if m := ION_OS.search(entry_norm):
            ver = canonicalize_version(m.group('ver'))
            keep.append(f"Ion OS v{ver}")
        elif m := PLANPOINT_OS.search(entry_norm):
            ver = canonicalize_version(m.group('ver'))
            keep.append(f"Plan Point OS v{ver}")

    return _dedupe(keep)


__all__ = ["filter_software_versions"]
