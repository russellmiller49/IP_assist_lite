"""Table-of-contents guardrails for IFU extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from medparse.ingest.models import PageData
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

TOC_KEYWORDS = (
    "table of contents",
    "contents",
    "index",
    "indice",
    "indice.",
    "summary of sections",
)
DOT_LEADER_RE = re.compile(r"\.{2,}\s*\d{1,3}\s*$")
PAGE_NUMBER_RE = re.compile(r"\b\d{1,3}\s*$")
SECTION_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+[A-Z][A-Za-z0-9 ,/&()-]{2,}$")
BLOCK_MAX_LINES = 6


@dataclass(slots=True)
class TocGuardConfig:
    """Runtime configuration for TOC detection heuristics."""

    enabled: bool = True
    density_threshold: float = 0.65
    dot_leader_min: float = 0.20
    page_number_ratio: float = 0.40
    scan_page_limit: int = 15
    min_dotted_lines: int = 2
    min_page_number_lines: int = 2

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, object]]) -> "TocGuardConfig":
        if not isinstance(data, dict):
            return cls()
        config = cls()
        config.update(data)
        return config

    def update(self, data: Dict[str, object]) -> None:
        for key, value in (data or {}).items():
            if not hasattr(self, key):
                continue
            current = getattr(self, key)
            if isinstance(current, bool):
                setattr(self, key, bool(value))
            elif isinstance(current, int):
                try:
                    setattr(self, key, int(value))
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    LOGGER.debug("Ignoring non-integer TOC guard override for %s: %r", key, value)
            else:
                try:
                    setattr(self, key, float(value))
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    LOGGER.debug("Ignoring non-numeric TOC guard override for %s: %r", key, value)

    def as_dict(self) -> Dict[str, int | float | bool]:
        return {
            "enabled": self.enabled,
            "density_threshold": self.density_threshold,
            "dot_leader_min": self.dot_leader_min,
            "page_number_ratio": self.page_number_ratio,
            "scan_page_limit": self.scan_page_limit,
            "min_dotted_lines": self.min_dotted_lines,
            "min_page_number_lines": self.min_page_number_lines,
        }


@dataclass(slots=True)
class TocGuardReport:
    """Runtime report produced by TOC guard processing."""

    enabled: bool
    pages_dropped: List[int] = field(default_factory=list)
    pages_considered: int = 0

    def to_metrics(self) -> Dict[str, object]:
        return {
            "enabled": self.enabled,
            "pages_dropped": list(self.pages_dropped),
            "pages_dropped_count": len(self.pages_dropped),
            "pages_considered": self.pages_considered,
        }


def apply_toc_guard(
    pages: Sequence[PageData],
    config: TocGuardConfig,
) -> Tuple[List[PageData], TocGuardReport]:
    """Drop TOC/index pages from the leading window."""

    if not config.enabled:
        return list(pages), TocGuardReport(enabled=False, pages_dropped=[], pages_considered=len(pages))

    filtered: List[PageData] = []
    dropped: List[int] = []
    limit = max(0, int(config.scan_page_limit))

    for idx, page in enumerate(pages):
        if idx < limit and _looks_like_toc_page(page, config):
            dropped.append(page.number)
            continue
        filtered.append(page)

    if dropped:
        LOGGER.debug("TOC guard dropped pages: %s", dropped)

    report = TocGuardReport(
        enabled=True,
        pages_dropped=dropped,
        pages_considered=min(len(pages), limit),
    )
    return filtered, report


def detect_first_chapter_page(pages: Sequence[PageData]) -> Optional[int]:
    """Return the first page number containing a numbered chapter heading."""

    for page in pages:
        for line in _iter_candidate_lines(page.lines):
            if SECTION_HEADING_RE.match(line) and not DOT_LEADER_RE.search(line):
                return page.number
    return None


def trim_anchor_bleed(text: str, *, max_blocks: int = 3, ratio_threshold: float = 0.8) -> Tuple[str, int]:
    """Remove leading TOC bleed from extracted anchor text."""

    if not text:
        return text, 0

    lines = text.splitlines()
    drop_count = _compute_bleed_prefix(lines, max_blocks=max_blocks, ratio_threshold=ratio_threshold)
    if drop_count <= 0:
        return text, 0

    trimmed_lines = lines[drop_count:]
    # Strip residual blank lines at the start after trimming
    while trimmed_lines and not trimmed_lines[0].strip():
        trimmed_lines.pop(0)
        drop_count += 1

    return "\n".join(trimmed_lines), drop_count


def _looks_like_toc_page(page: PageData, config: TocGuardConfig) -> bool:
    if not page.lines:
        return False

    lines = [line.strip() for line in page.lines if line.strip()]
    if not lines:
        return False

    lowered_lines = [line.lower() for line in lines]
    for keyword in TOC_KEYWORDS:
        if any(line.startswith(keyword) for line in lowered_lines):
            return True

    dotted_lines = sum(1 for line in lines if DOT_LEADER_RE.search(line))
    numbered_lines = sum(1 for line in lines if PAGE_NUMBER_RE.search(line))
    short_lines = sum(1 for line in lines if len(line) <= 80)

    total_lines = len(lines)
    if total_lines == 0:
        return False

    dotted_ratio = dotted_lines / total_lines
    numbered_ratio = numbered_lines / total_lines

    if dotted_lines >= config.min_dotted_lines and numbered_lines >= config.min_page_number_lines:
        return True

    if dotted_ratio >= config.dot_leader_min and numbered_ratio >= config.page_number_ratio:
        return True

    if total_lines >= 4 and numbered_ratio >= 0.5 and short_lines / total_lines >= 0.7:
        return True

    # Guard for sequences of numbered headings (e.g., chapter lists)
    heading_hits = sum(1 for line in lines if _looks_like_section_candidate(line))
    if total_lines >= 5 and heading_hits >= 4 and numbered_ratio >= 0.3:
        return True

    return False


def _compute_bleed_prefix(
    lines: List[str],
    *,
    max_blocks: int,
    ratio_threshold: float,
) -> int:
    drop = 0
    block: List[str] = []
    block_count = 0
    idx = 0
    total_lines = len(lines)

    while idx < total_lines and block_count < max_blocks:
        line = lines[idx]
        block.append(line)
        idx += 1

        block_complete = False
        if not line.strip():
            block_complete = True
        elif len(block) >= BLOCK_MAX_LINES:
            block_complete = True
        elif idx == total_lines:
            block_complete = True

        if not block_complete:
            continue

        non_empty = [candidate for candidate in block if candidate.strip()]
        if not non_empty:
            drop += len(block)
            block = []
            block_count += 1
            continue

        toc_lines = sum(1 for candidate in non_empty if _is_toc_line(candidate))
        ratio = toc_lines / len(non_empty)

        if ratio >= ratio_threshold:
            drop += len(block)
            block = []
            block_count += 1
            continue

        break

    return drop


def _iter_candidate_lines(lines: Iterable[str]) -> Iterable[str]:
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped:
            yield stripped


def _is_toc_line(line: str) -> bool:
    lowered = line.lower()
    if any(keyword in lowered for keyword in TOC_KEYWORDS):
        return True
    if DOT_LEADER_RE.search(line):
        return True
    if PAGE_NUMBER_RE.search(line) and len(line.strip()) <= 90:
        return True
    return False


def _looks_like_section_candidate(line: str) -> bool:
    if DOT_LEADER_RE.search(line):
        return True
    return bool(SECTION_HEADING_RE.match(line))


__all__ = [
    "TocGuardConfig",
    "TocGuardReport",
    "apply_toc_guard",
    "detect_first_chapter_page",
    "trim_anchor_bleed",
]
