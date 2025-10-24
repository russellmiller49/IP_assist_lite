"""Layout analysis helpers (headings, sections, callouts)."""

from __future__ import annotations

import re
from statistics import median
from typing import List, Optional, Sequence

from medparse.ingest.models import Heading, PageData, TextBlock

ANCHOR_KEYWORDS = {
    "abstract": "Abstract",
    "keywords": "Keywords",
    "indications for use": "Indications for Use",
    "intended use": "Intended Use",
    "warnings": "Warnings",
    "caution": "Caution",
    "note": "Note",
    "references": "References",
    "bibliography": "Bibliography",
}

CALLOUT_PATTERN = re.compile(r"^(warning|caution|note|⚠|❗)", re.IGNORECASE)
BULLET_PREFIX = re.compile(r"^([-\u2022\u2023\u25E6*]\s+|\d+[.)]\s+)")


def detect_headings(page: PageData) -> List[Heading]:
    """Detect section headings for a page using typography and anchors."""

    if not page.blocks:
        return _anchor_headings(page)

    font_sizes = [block.font_size for block in page.blocks if block.font_size]
    headings: List[Heading] = []
    seen_positions: set[tuple[int, int]] = set()

    base_size = median(font_sizes) if font_sizes else 0.0
    threshold = base_size * 1.12 if base_size else 11.0

    for block in page.blocks:
        if not _is_heading_candidate(block, base_size, threshold):
            continue
        title = _clean_heading(block.text)
        if not title:
            continue
        line_index = _find_line_index(page.lines, title)
        if line_index is None:
            continue
        key = (page.number, line_index)
        if key in seen_positions:
            continue
        seen_positions.add(key)

        level = _infer_level(block, base_size)
        kind = "callout" if _is_callout(title) else "section"
        headings.append(
            Heading(
                title=title,
                page=page.number,
                line_index=line_index,
                level=level,
                kind=kind,
            )
        )

    headings.extend(_anchor_headings(page, seen_positions))
    headings.sort(key=lambda h: (h.page, h.line_index))
    return headings


def _is_heading_candidate(block: TextBlock, base_size: float, threshold: float) -> bool:
    if not block.text:
        return False
    text = block.text.strip()
    if len(text) <= 2:
        return False
    if BULLET_PREFIX.match(text):
        return False
    if block.font_size and block.font_size >= threshold:
        return True
    if block.is_bold and block.font_size and block.font_size >= base_size * 1.05:
        return True
    if text.isupper() and len(text.split()) <= 12:
        return True
    if block.font_size is None and text.istitle() and len(text.split()) <= 8:
        return True
    return False


def _clean_heading(text: str) -> Optional[str]:
    cleaned = text.strip().strip(":")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) < 4:
        return None
    if cleaned.lower().startswith("figure"):
        return None
    if cleaned.lower().startswith("table"):
        return None
    return cleaned


def _find_line_index(lines: Sequence[str], title: str) -> Optional[int]:
    norm = title.lower()
    for idx, line in enumerate(lines):
        if norm in line.lower():
            return idx
    return None


def _infer_level(block: TextBlock, base_size: float) -> Optional[int]:
    if not block.font_size or not base_size:
        return None
    ratio = block.font_size / base_size if base_size else 1.0
    if ratio >= 1.5:
        return 1
    if ratio >= 1.25:
        return 2
    if ratio >= 1.1:
        return 3
    return 4


def _is_callout(title: str) -> bool:
    return bool(CALLOUT_PATTERN.match(title))


def _anchor_headings(page: PageData, seen: Optional[set[tuple[int, int]]] = None) -> List[Heading]:
    seen = seen or set()
    anchors: List[Heading] = []
    for idx, line in enumerate(page.lines):
        normalized = line.strip().lower()
        for needle, title in ANCHOR_KEYWORDS.items():
            if needle in normalized:
                key = (page.number, idx)
                if key in seen:
                    continue
                seen.add(key)
                anchors.append(
                    Heading(
                        title=title,
                        page=page.number,
                        line_index=idx,
                        level=None,
                        kind="callout" if _is_callout(title) else "section",
                    )
                )
    return anchors


__all__ = ["detect_headings"]
