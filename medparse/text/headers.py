"""Boilerplate stripping helpers for common guideline PDFs."""

from __future__ import annotations

import re
from typing import Iterable

BOILERPLATE_PATTERNS = [
    re.compile(r"^american thoracic society documents\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*volume\s+\d+.*\|\s*(january|february|march|april|may|june|"
               r"july|august|september|october|november|december)\s+\d{1,2}\s*\d{4}\s*$",
               re.IGNORECASE),
    re.compile(r"^\s*american thoracic society\s+documents\s*$", re.IGNORECASE),
    re.compile(r"^\s*official american thoracic society documents\s*$", re.IGNORECASE),
]


def is_boilerplate_line(text: str | None) -> bool:
    """Return True if ``text`` matches a known header/footer boilerplate pattern."""

    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in BOILERPLATE_PATTERNS)


def strip_boilerplate(lines: Iterable[str]) -> list[str]:
    """Remove boilerplate lines from the given iterable while preserving order."""

    return [line for line in lines if not is_boilerplate_line(line)]


__all__ = ["is_boilerplate_line", "strip_boilerplate"]

