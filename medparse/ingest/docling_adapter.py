"""Lightweight adapter that runs Docling on targeted pages."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)


@dataclass
class DoclingTable:
    page: int
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    caption: Optional[str] = None
    label: Optional[str] = None


@dataclass
class DoclingArtifacts:
    tables: List[DoclingTable] = field(default_factory=list)
    safety_blocks: List[dict] = field(default_factory=list)
    pages_processed: List[int] = field(default_factory=list)
    duration_s: float = 0.0


class DoclingAdapter:
    """Encapsulates Docling conversion with minimal error handling."""

    def __init__(self) -> None:
        self._converter = None

    def extract(
        self,
        pdf_path: Path,
        *,
        doc_type: str,
        pages: Sequence[int],
    ) -> DoclingArtifacts:
        normalized_pages = sorted({int(page) for page in pages if isinstance(page, int) and page > 0})
        if not normalized_pages:
            return DoclingArtifacts()
        converter = self._ensure_converter()
        tables: List[DoclingTable] = []
        processed: set[int] = set()
        start = time.perf_counter()
        for page in normalized_pages:
            try:
                result = converter.convert(pdf_path, page_range=(page, page))
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Docling conversion failed for page %s: %s", page, exc)
                continue
            doc = getattr(result, "document", None)
            if doc is None:
                continue
            page_tables = getattr(doc, "tables", []) or []
            for table in page_tables:
                page_no = _resolve_table_page(table, fallback=page)
                processed.add(page_no)
                converted = _convert_table_item(table, page_no)
                if converted is not None:
                    tables.append(converted)
        duration = time.perf_counter() - start
        return DoclingArtifacts(
            tables=tables,
            pages_processed=sorted(processed),
            duration_s=duration,
        )

    def _ensure_converter(self):
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("Docling converter is not available") from exc
            self._converter = DocumentConverter()
        return self._converter


def _resolve_table_page(table: object, fallback: int) -> int:
    prov = getattr(table, "prov", None)
    if prov:
        first = prov[0]
        if isinstance(first, dict):
            try:
                return int(first.get("page_no", fallback) or fallback)
            except (TypeError, ValueError):
                return fallback
        try:
            return int(getattr(first, "page_no", fallback) or fallback)
        except (TypeError, ValueError):
            return fallback
    return fallback


def _convert_table_item(table: object, page_no: int) -> Optional[DoclingTable]:
    data = getattr(table, "data", None)
    if data is None:
        return None
    num_rows = getattr(data, "num_rows", 0) or 0
    num_cols = getattr(data, "num_cols", 0) or 0
    if num_rows <= 0 or num_cols <= 0:
        return None
    grid: List[List[str]] = [["" for _ in range(num_cols)] for _ in range(num_rows)]
    cells = getattr(data, "table_cells", []) or []
    for cell in cells:
        text = (getattr(cell, "text", "") or "").strip()
        row = getattr(cell, "start_row_offset_idx", None)
        col = getattr(cell, "start_col_offset_idx", None)
        if row is None or col is None:
            continue
        if 0 <= row < num_rows and 0 <= col < num_cols:
            grid[row][col] = text
    header_row = grid[0] if grid else []
    body_rows = [list(row) for row in grid[1:]] if len(grid) > 1 else []
    caption = _extract_caption(table)
    label_value = getattr(table, "label", None)
    label = str(label_value.value) if hasattr(label_value, "value") else (str(label_value) if label_value else None)
    return DoclingTable(
        page=page_no,
        headers=list(header_row),
        rows=body_rows,
        caption=caption,
        label=label,
    )


def _extract_caption(table: object) -> Optional[str]:
    caption_fn = getattr(table, "caption_text", None)
    if callable(caption_fn):
        try:
            text = caption_fn()
            if text:
                stripped = str(text).strip()
                if stripped:
                    return stripped
        except Exception:  # pragma: no cover - defensive
            pass
    captions = getattr(table, "captions", None)
    if captions:
        first = captions[0]
        if isinstance(first, dict):
            text = first.get("text")
        else:
            text = getattr(first, "text", None)
        if text:
            stripped = str(text).strip()
            if stripped:
                return stripped
    return None


__all__ = [
    "DoclingAdapter",
    "DoclingArtifacts",
    "DoclingTable",
]
