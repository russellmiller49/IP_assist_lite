"""Boilerplate stripping helpers for common guideline PDFs and IFUs."""

from __future__ import annotations

import re
from typing import Iterable, List

# Medical society boilerplate
BOILERPLATE_PATTERNS = [
    re.compile(r"^american thoracic society documents\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*volume\s+\d+.*\|\s*(january|february|march|april|may|june|"
               r"july|august|september|october|november|december)\s+\d{1,2}\s*\d{4}\s*$",
               re.IGNORECASE),
    re.compile(r"^\s*american thoracic society\s+documents\s*$", re.IGNORECASE),
    re.compile(r"^\s*official american thoracic society documents\s*$", re.IGNORECASE),
]

# Common header patterns
HEADER_PATTERNS = [
    # Simple page headers
    re.compile(r"^page\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE),
    # Pure page numbers
    re.compile(r"^\d{1,4}$"),
    # Header with document title (common in IFUs)
    re.compile(r"^(?:instruction|user|operator)s?\s+(?:manual|guide|handbook)\s+(?:for|‑)?\s*.*\d+\s*$", re.IGNORECASE),
]

# Common footer patterns
FOOTER_PATTERNS = [
    # Page X / Y or X/Y format
    re.compile(r"^\d+\s*/\s*\d+$"),
    re.compile(r"^page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE),
    # Document part numbers at bottom
    re.compile(r"^[A-Z]{2,4}[-\s]?\d{4,8}(?:[-\s][A-Z0-9]{1,4})?\s*$"),
    # Copyright notices
    re.compile(r"^©\s*\d{4}.*$"),
    re.compile(r"^copyright\s+©?\s*\d{4}.*$", re.IGNORECASE),
    # Common IFU footer formats (e.g., "ALT-Pro INSTRUCTION MANUAL 33")
    re.compile(r"^(?:.*)?(?:instruction|user|operator)s?\s+(?:manual|guide)\s+\d+\s*$", re.IGNORECASE),
    # Model/Part number footers
    re.compile(r"^(?:model|part|catalog|ref)(?:\s+(?:no\.?|number))?\s*[:#]?\s*[A-Z0-9\-/]+\s*$", re.IGNORECASE),
]

# Persistent running headers that appear on every page
RUNNING_HEADER_PATTERNS = [
    # Document classification
    re.compile(r"^(?:confidential|proprietary|internal\s+use\s+only)\s*$", re.IGNORECASE),
    # Chapter/section headers that repeat
    re.compile(r"^chapter\s+\d+", re.IGNORECASE),
]


def is_boilerplate_line(text: str | None) -> bool:
    """Return True if ``text`` matches a known header/footer boilerplate pattern."""

    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in BOILERPLATE_PATTERNS)


def is_header_line(text: str | None) -> bool:
    """Return True if text matches a common header pattern."""
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in HEADER_PATTERNS + RUNNING_HEADER_PATTERNS)


def is_footer_line(text: str | None) -> bool:
    """Return True if text matches a common footer pattern."""
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in FOOTER_PATTERNS)


def strip_boilerplate(lines: Iterable[str]) -> list[str]:
    """Remove boilerplate lines from the given iterable while preserving order."""

    return [line for line in lines if not is_boilerplate_line(line)]


def strip_headers_and_footers(
    lines: List[str],
    *,
    strip_headers: bool = True,
    strip_footers: bool = True,
    aggressive: bool = False,
) -> List[str]:
    """Remove headers and footers from a list of lines.

    Args:
        lines: Input lines
        strip_headers: Remove header lines
        strip_footers: Remove footer lines
        aggressive: Also remove running headers and persistent footers

    Returns:
        Cleaned lines
    """
    if not lines:
        return lines

    result = list(lines)

    # Strip first line if it's a header
    if strip_headers and result:
        if is_header_line(result[0]) or (aggressive and is_boilerplate_line(result[0])):
            result = result[1:]

    # Strip last line if it's a footer
    if strip_footers and result:
        if is_footer_line(result[-1]) or (aggressive and is_boilerplate_line(result[-1])):
            result = result[:-1]

    return result


def detect_repeating_header_footer(
    all_page_lines: List[List[str]],
    *,
    min_occurrences: int = 3,
) -> tuple[List[str], List[str]]:
    """Detect repeating headers/footers across pages.

    Args:
        all_page_lines: List of line lists (one per page)
        min_occurrences: Minimum pages a line must appear on to be considered repeating

    Returns:
        Tuple of (repeating_headers, repeating_footers)
    """
    if len(all_page_lines) < min_occurrences:
        return [], []

    # Count first line occurrences (potential headers)
    first_lines: dict[str, int] = {}
    for page_lines in all_page_lines:
        if page_lines:
            normalized = page_lines[0].strip()
            if normalized:
                first_lines[normalized] = first_lines.get(normalized, 0) + 1

    # Count last line occurrences (potential footers)
    last_lines: dict[str, int] = {}
    for page_lines in all_page_lines:
        if page_lines:
            normalized = page_lines[-1].strip()
            if normalized:
                last_lines[normalized] = last_lines.get(normalized, 0) + 1

    # Filter by minimum occurrences
    repeating_headers = [
        line for line, count in first_lines.items()
        if count >= min_occurrences
    ]

    repeating_footers = [
        line for line, count in last_lines.items()
        if count >= min_occurrences
    ]

    return repeating_headers, repeating_footers


__all__ = [
    "is_boilerplate_line",
    "is_header_line",
    "is_footer_line",
    "strip_boilerplate",
    "strip_headers_and_footers",
    "detect_repeating_header_footer",
]

