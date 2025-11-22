"""Table extraction helpers used by the ingestion pipeline."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, List, Sequence

from src.contracts.schema import ExtractionResult, TableData

from medparse.tables.extractor import extract_tables  # noqa: F401

LOGGER = logging.getLogger(__name__)


def rescue_tables_with_pdfplumber(pdf_path: Path, pages_idx: Sequence[int]) -> List[TableData]:
    """Run a lightweight pdfplumber pass on the requested pages."""

    try:
        import pdfplumber  # type: ignore[import-not-found]
    except Exception:
        LOGGER.warning("pdfplumber is not available; skipping table rescue")
        return []

    normalized = sorted({idx for idx in pages_idx if isinstance(idx, int) and idx >= 0})
    if not normalized:
        return []

    rescued: List[TableData] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            for idx in normalized:
                if idx >= total_pages:
                    continue
                page = pdf.pages[idx]
                tables = page.extract_tables(
                    table_settings={
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                    }
                )
                if not tables:
                    continue
                for local_idx, raw in enumerate(tables, start=1):
                    if not raw or not any(any(cell.strip() for cell in row if isinstance(cell, str)) for row in raw):
                        continue
                    table_id = f"rescued_{idx+1}_{local_idx:02d}"
                    caption = f"Table {local_idx} (rescued)"
                    description = _flatten_table_description(raw, caption)
                    rescued.append(
                        TableData(
                            id=table_id,
                            caption=caption,
                            data=[list(row) for row in raw],
                            metadata={
                                "source": "pdfplumber",
                                "page": idx + 1,
                                "flattened_description": description,
                            },
                        )
                    )
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("pdfplumber rescue failed: %s", exc)
        return []
    return rescued


def ensure_tables(document: ExtractionResult, pdf_path: Path) -> ExtractionResult:
    """Ensure that table payloads are non-empty by falling back to pdfplumber."""

    path = Path(pdf_path)
    if not path.exists():
        return document

    existing = list(document.tables or [])
    # Drop obvious false positives (single-column narrative fragments).
    filtered_existing: List[TableData] = []
    dropped = 0
    for table in existing:
        if _looks_like_narrative_table(table):
            dropped += 1
            continue
        filtered_existing.append(table)
    existing = filtered_existing
    if dropped:
        LOGGER.info("Dropped %s suspect narrative table(s) before rescue", dropped)

    if not existing:
        pages = _pages_with_table_markers(path)
        rescued = rescue_tables_with_pdfplumber(path, pages)
        if rescued:
            document.tables = rescued
            _refresh_table_sentences(document)
        return document

    empties = [table for table in existing if _is_table_empty(table)]
    if not empties:
        # Even when all tables are non-empty, append rescued tables from marker pages
        marker_pages = _pages_with_table_markers(path)
        rescued_extra = rescue_tables_with_pdfplumber(path, marker_pages)
        if rescued_extra:
            merged = list(existing)
            seen_keys = {(tbl.metadata.get("page"), tbl.caption) for tbl in merged if tbl.metadata}
            for tbl in rescued_extra:
                key = (tbl.metadata.get("page") if tbl.metadata else None, tbl.caption)
                if key in seen_keys:
                    continue
                merged.append(tbl)
            document.tables = merged
            _refresh_table_sentences(document)
        return document

    target_pages: List[int] = []
    for table in empties:
        page = _table_page_hint(table)
        if page is not None:
            target_pages.append(page - 1)
    target_pages.extend(_pages_with_table_markers(path))
    rescued = rescue_tables_with_pdfplumber(path, target_pages)
    if not rescued:
        return document

    replacement_iter = iter(rescued)
    merged: List[TableData] = []
    for table in existing:
        if _is_table_empty(table):
            try:
                merged.append(next(replacement_iter))
            except StopIteration:
                merged.append(table)
        else:
            merged.append(table)

    merged.extend(list(replacement_iter))
    document.tables = merged
    _refresh_table_sentences(document)
    return document


def _is_table_empty(table: TableData) -> bool:
    data = table.data or []
    if not data:
        return True
    flattened = "".join(str(cell or "").strip() for row in data for cell in row)
    if not flattened:
        return True
    if len(data) == 1:
        # header-only table
        return True
    return False


def _table_page_hint(table: TableData) -> int | None:
    meta = table.metadata or {}
    for key in ("page", "page_number", "pageNo", "page_no"):
        value = meta.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def _pages_with_table_markers(pdf_path: Path) -> List[int]:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except Exception:
        return []

    markers: List[int] = []
    pattern = re.compile(r"Table\s*\d", re.IGNORECASE)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if pattern.search(text):
                    markers.append(idx)
    except Exception:
        return []
    return markers


def _looks_like_narrative_table(table: TableData) -> bool:
    data = table.data or []
    if len(data) < 3:
        return False
    max_cols = max(len(row) for row in data if isinstance(row, list)) if data else 0
    if max_cols > 1:
        return False

    total_cells = 0
    long_cells = 0
    for row in data:
        for cell in row:
            text = str(cell or "").strip()
            if not text:
                continue
            total_cells += 1
            if len(text) >= 120:
                long_cells += 1
    if total_cells == 0:
        return False
    return (long_cells / total_cells) >= 0.6


def _flatten_table_description(data: Sequence[Sequence[str]], caption: str | None = None) -> str:
    lines: List[str] = []
    if caption:
        lines.append(f"Table caption: {caption}.")
    if not data:
        return "Empty table."
    headers = data[0]
    rows = data[1:]
    for row in rows:
        for idx, cell in enumerate(row):
            header = headers[idx] if idx < len(headers) else f"Column {idx+1}"
            cell_text = str(cell or "").strip()
            if not cell_text:
                continue
            lines.append(f"{header}: {cell_text}.")
    return " ".join(lines) if lines else "Empty table."


def _refresh_table_sentences(document: ExtractionResult) -> None:
    sentences = list(document.table_sentences or [])
    existing_ids = {entry.get("table_id") for entry in sentences if isinstance(entry, dict)}
    for table in document.tables:
        if table.id in existing_ids:
            continue
        metadata = table.metadata or {}
        description = metadata.get("flattened_description")
        if not description:
            continue
        sentences.append({
            "text": description,
            "table_id": table.id,
            "caption": table.caption,
        })
    document.table_sentences = sentences


__all__ = [
    "ensure_tables",
    "extract_tables",
    "rescue_tables_with_pdfplumber",
]
