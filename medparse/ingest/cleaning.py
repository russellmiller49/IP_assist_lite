"""Utilities for normalising section text during ingestion."""

from __future__ import annotations

import re
from typing import Iterable, List

LIGATURE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("\ufb01", "fi"),
    ("\ufb02", "fl"),
    ("/uniFB01", "fi"),
    ("/uniFB02", "fl"),
    ("\u00b7", "·"),
)


def normalize_text_artifacts(text: str) -> str:
    """Replace common ligature artifacts and tidy whitespace."""

    if not text:
        return ""

    normalised = text
    for source, target in LIGATURE_REPLACEMENTS:
        normalised = normalised.replace(source, target)

    # Collapse spaces introduced by ligature replacement (e.g., "fi stula" -> "fistula").
    normalised = re.sub(r"(?i)(f[il])\s+([a-z])", r"\1\2", normalised)
    # Remove stray spaces around newlines and collapse repeated spaces.
    normalised = re.sub(r"[ \t]+\n", "\n", normalised)
    normalised = re.sub(r"\n[ \t]+", "\n", normalised)
    normalised = re.sub(r"[ \t]{2,}", " ", normalised)
    return normalised

HEADER_RE = re.compile(r"^[A-Z0-9\s\-\|]{6,}$")
CALLOUT_HEADER_RE = re.compile(
    r"^(?:box\s*\d+[A-Za-z]?|!+|warning|caution|note)\b", re.IGNORECASE
)
BULLET_RE = re.compile(r"^([-•●◦*]\s+|\d+\.\s+)")


def sanitize_sections(lines: Iterable[str]) -> List[str]:
    """Drop noisy headers and collapse whitespace within section text."""
    cleaned: List[str] = []
    previous: str | None = None

    for raw in lines:
        if raw is None:
            continue
        line = normalize_text_artifacts(raw).strip()
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        if HEADER_RE.match(line) and not CALLOUT_HEADER_RE.match(line):
            # Skip likely running headers.
            continue

        if BULLET_RE.match(line):
            normalised = re.sub(r"\s+", " ", line)
        else:
            normalised = re.sub(r"\s+", " ", line).strip()
        normalised = re.sub(r"\s*:\s*", ": ", normalised)

        if normalised == previous and not CALLOUT_HEADER_RE.match(normalised):
            continue

        cleaned.append(normalised)
        previous = normalised

    # Trim trailing blank lines for determinism.
    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    return cleaned
