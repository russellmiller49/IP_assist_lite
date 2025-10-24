"""Parse and normalise IFU front-matter using manufacturer profiles."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from medparse.manufacturers import PROFILES, ManufacturerProfile, detect_manufacturer

# False positive patterns to avoid (e.g., "ERSEENGINEER" matching as revision)
FALSE_POSITIVE_PATTERNS = [
    r'\bENGINEER\b',
    r'\bDRAFT\b',
    r'\bTable\s+of\s+Contents\b',
    r'\bAppendix\b',
    r'\bChapter\b',
]

FALSE_POSITIVE_RE = re.compile('|'.join(FALSE_POSITIVE_PATTERNS), re.IGNORECASE)


def normalize_pub_date(s: str) -> Optional[str]:
    """Normalize publication date to YYYY-MM-DD format.

    Handles formats:
    - YYYY-MM → YYYY-MM-01
    - Month YYYY → YYYY-MM-01
    - DD.MM.YYYY → YYYY-MM-DD (ERBE format)
    """
    s = s.strip()

    # Handle DD.MM.YYYY format (ERBE)
    m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', s)
    if m:
        day, month, year = m.groups()
        return f"{year}-{month}-{day}"

    # Remove spaces from date separators: "2024. 08" -> "2024.08"
    s = re.sub(r'(\d{4})\s*[.\-]\s*(\d{2})', r'\1-\2', s)

    try:
        # Normalize "Aug 2024" -> 2024-08-01; "2024-08" -> 2024-08-01
        if re.match(r'^\d{4}-\d{2}$', s):
            return f"{s}-01"
        dt = datetime.strptime(s, "%b %Y")
        return dt.strftime("%Y-%m-01")
    except Exception:
        # Try long month
        try:
            dt = datetime.strptime(s, "%B %Y")
            return dt.strftime("%Y-%m-01")
        except Exception:
            return None


def _extract_with_profile(
    text: str,
    profile: ManufacturerProfile
) -> Dict[str, Optional[str]]:
    """Extract front-matter using manufacturer-specific patterns.

    Args:
        text: Text from cover pages
        profile: Manufacturer profile with patterns

    Returns:
        Dictionary with extracted fields
    """
    data: Dict[str, Optional[str]] = {
        "part_number": None,
        "revision": None,
        "publication_date": None,
        "model": None,
        "manufacturer": profile.name,
        "product_name": None,
    }

    # Part number
    for pattern in profile.pn_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m and not FALSE_POSITIVE_RE.search(m.group(0)):
            data["part_number"] = m.group(1)
            break

    # Revision
    for pattern in profile.rev_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m and not FALSE_POSITIVE_RE.search(m.group(0)):
            # Extract the captured group (revision letter/number)
            rev = m.group(1) if m.lastindex else m.group(0)
            data["revision"] = rev
            break

    # Publication date
    for pattern in profile.date_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            date_str = m.group(0)
            normalized = normalize_pub_date(date_str)
            if normalized:
                data["publication_date"] = normalized
                break

    # Model
    for pattern in profile.model_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            model = m.group(1) if m.lastindex else m.group(0)
            data["model"] = model
            break

    # Apply profile-specific normalization
    data = profile.normalize(data)

    return data


def extract_front_matter_from_text(
    lines: Iterable[str],
    profile: Optional[ManufacturerProfile] = None
) -> Dict[str, Optional[str]]:
    """Extract front-matter fields from text lines.

    Args:
        lines: Iterable of text lines (from cover or appendix pages)
        profile: Optional manufacturer profile (auto-detected if None)

    Returns:
        Dictionary with part_number, revision, publication_date, model, manufacturer, product_name
    """
    text = "\n".join(lines)

    # Detect manufacturer profile if not provided
    if profile is None:
        profile = detect_manufacturer(text, PROFILES)

    if profile:
        return _extract_with_profile(text, profile)

    # Fallback to empty data if no profile matched
    return {
        "part_number": None,
        "revision": None,
        "publication_date": None,
        "model": None,
        "manufacturer": None,
        "product_name": None,
    }


def parse_front_matter(pages_text: List[str]) -> Dict[str, Optional[str]]:
    """Extract PN/Rev, publication date, model, manufacturer from cover pages.

    Uses windowed search: cover pages (0-2) first, then back pages (last 3) as fallback.
    Auto-detects manufacturer and uses appropriate extraction patterns.

    Args:
        pages_text: List of page text strings

    Returns:
        Dictionary with front-matter fields (None if not found)
    """
    if not pages_text:
        return {
            "part_number": None,
            "revision": None,
            "publication_date": None,
            "model": None,
            "manufacturer": None,
            "product_name": None,
        }

    # Cover pass: first 3 pages (0, 1, 2)
    cover_idxs = [0, 1, 2]
    cover_lines = [pages_text[i] for i in cover_idxs if i < len(pages_text)]
    cover_text = "\n".join(cover_lines)

    # Detect manufacturer from cover
    profile = detect_manufacturer(cover_text, PROFILES)

    # Extract with profile
    fm = extract_front_matter_from_text(cover_lines, profile)

    # Appendix fallback: last 3 pages (if any fields missing)
    if not all([fm.get("part_number"), fm.get("revision"), fm.get("publication_date"), fm.get("model")]):
        tail_idxs = [max(0, len(pages_text) - 3), max(0, len(pages_text) - 2), max(0, len(pages_text) - 1)]
        tail_lines = [pages_text[i] for i in tail_idxs if i < len(pages_text)]
        fm_tail = extract_front_matter_from_text(tail_lines, profile)

        # Fill in missing fields from tail
        for k, v in fm_tail.items():
            if not fm.get(k):
                fm[k] = v

    return fm


__all__ = ["parse_front_matter", "extract_front_matter_from_text", "normalize_pub_date"]
