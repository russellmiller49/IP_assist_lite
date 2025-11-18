"""Lightweight data containers for PDF ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

# Word box: (x0, y0, x1, y1, text)
WordBox = Tuple[float, float, float, float, str]


@dataclass(slots=True)
class TextBlock:
    """Normalized text block with layout metadata."""

    text: str
    bbox: Optional[Tuple[float, float, float, float]]
    font_size: Optional[float]
    is_bold: bool


@dataclass(slots=True)
class Heading:
    """Boundary representing a section heading or callout."""

    title: str
    page: int
    line_index: int
    level: Optional[int] = None
    kind: Literal["section", "callout"] = "section"


@dataclass(slots=True)
class TableData:
    """Representation of a table detected on a page."""

    title: Optional[str]
    headers: List[str]
    rows: List[List[str]]
    page: int
    caption: Optional[str] = None
    footnotes: List[str] = field(default_factory=list)
    heading_path: List[str] = field(default_factory=list)
    rows_truncated: bool = False


@dataclass(slots=True)
class PageData:
    """Aggregated data per PDF page emitted by ``iter_pages``."""

    number: int
    text: str
    lines: List[str] = field(default_factory=list)
    blocks: List[TextBlock] = field(default_factory=list)
    headings: List[Heading] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)
    word_boxes: List[WordBox] = field(default_factory=list)  # For word-level spacing restoration
    ocr_applied: bool = False
    column_map: Dict[int, int] = field(default_factory=dict)
    normalization_report: Dict[str, int] = field(default_factory=dict)
