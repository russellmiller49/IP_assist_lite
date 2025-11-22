"""Heuristics that determine which pages should run Docling augmentations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence

from medparse.ingest.models import PageData

TABLE_HEADER_RE = re.compile(r"\btable\s*\d+\b", re.IGNORECASE)
SAFETY_RE = re.compile(r"\b(?:warning|caution|danger|important information)\b", re.IGNORECASE)
GRIDLINE_RE = re.compile(r"\|{2,}")


@dataclass(frozen=True)
class DoclingPageTargets:
    """Grouped page selections for Docling."""

    table_pages: List[int]
    safety_pages: List[int]
    forced_pages: List[int]

    @property
    def all_pages(self) -> List[int]:
        combined = {page for page in (*self.table_pages, *self.safety_pages, *self.forced_pages) if page}
        return sorted(combined)


def analyze_docling_targets(
    pages: Sequence[PageData],
    *,
    force_pages: Sequence[int] | None = None,
) -> DoclingPageTargets:
    table_pages: List[int] = []
    safety_pages: List[int] = []
    for idx, page in enumerate(pages):
        page_no = page.number or idx + 1
        if page_no < 1:
            continue
        if is_table_page(page):
            if page_no not in table_pages:
                table_pages.append(page_no)
        if is_safety_page(page):
            if page_no not in safety_pages:
                safety_pages.append(page_no)
    forced = [] if not force_pages else _dedupe(force_pages)
    return DoclingPageTargets(table_pages=table_pages, safety_pages=safety_pages, forced_pages=forced)


def is_table_page(page: PageData) -> bool:
    if not page:
        return False
    if getattr(page, "tables", None):
        return True
    lines = page.lines[:8]
    if any(TABLE_HEADER_RE.search(line or "") for line in lines):
        return True
    text = page.text or ""
    if _numeric_density(text) > 0.35:
        return True
    grid_hits = sum(len(GRIDLINE_RE.findall(line or "")) for line in lines)
    return grid_hits >= 3


def is_safety_page(page: PageData) -> bool:
    if not page:
        return False
    text = page.text or ""
    if SAFETY_RE.search(text):
        return True
    uppercase_hits = sum(1 for line in page.lines[:20] if line.strip().isupper() and len(line.strip()) > 6)
    return uppercase_hits >= 3


def _numeric_density(text: str) -> float:
    if not text:
        return 0.0
    digits = sum(1 for ch in text if ch.isdigit())
    return digits / max(1, len(text))


def _dedupe(values: Sequence[int]) -> List[int]:
    seen: set[int] = set()
    ordered: List[int] = []
    for value in values:
        try:
            page = int(value)
        except (TypeError, ValueError):
            continue
        if page <= 0 or page in seen:
            continue
        seen.add(page)
        ordered.append(page)
    return ordered


__all__ = [
    "DoclingPageTargets",
    "analyze_docling_targets",
    "is_table_page",
    "is_safety_page",
]
