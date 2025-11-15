"""Table extraction helpers using pdfplumber heuristics."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from medparse.ingest.models import TableData

TABLE_HEADER_RE = re.compile(r"\btable\s*\d", re.IGNORECASE)

TABLE_KEYWORDS = (
    "table",
    "status indicator",
    "led",
    "power button",
    "complication",
    "sensitivity",
    "specificity",
    "adverse event",
)


def _looks_like_dense_grid(text: str) -> bool:
    lines = text.splitlines()
    dense_rows = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = re.split(r"\s{3,}", stripped)
        if len(parts) >= 3 and all(part for part in parts[:3]):
            dense_rows += 1
        if dense_rows >= 2:
            return True
    return False

try:
    import pdfplumber  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None  # type: ignore


def extract_tables(pdf_path: Path, page_number: int, page_text: str) -> List[TableData]:
    """Extract tables for a page when context suggests structured data."""

    lower_text = page_text.lower()
    force_scan = bool(TABLE_HEADER_RE.search(page_text)) or _looks_like_dense_grid(page_text)
    if not force_scan and not any(keyword in lower_text for keyword in TABLE_KEYWORDS):
        return []

    if pdfplumber is None:
        return _extract_inline_tables(page_text, page_number)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_number - 1]
            found: List[TableData] = []
            for raw_table in page.extract_tables() or []:
                if not raw_table:
                    continue
                headers, rows = _split_table(raw_table)
                title = _detect_table_title(page_text, headers)
                found.append(TableData(title=title, headers=headers, rows=rows, page=page_number))
            if found:
                return found
            table_settings = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "intersection_tolerance": 5,
            }
            tuned_tables = page.extract_tables(table_settings=table_settings) or []
            for raw_table in tuned_tables:
                if not raw_table:
                    continue
                headers, rows = _split_table(raw_table)
                title = _detect_table_title(page_text, headers)
                found.append(TableData(title=title, headers=headers, rows=rows, page=page_number))
            if found:
                return found
    except Exception:
        pass
    return _extract_inline_tables(page_text, page_number)


def _split_table(raw_table: List[List[Optional[str]]]) -> tuple[List[str], List[List[str]]]:
    normalized_rows: List[List[str]] = [
        [cell.strip() if isinstance(cell, str) else "" for cell in row]
        for row in raw_table
    ]
    headers = normalized_rows[0] if normalized_rows else []
    body = normalized_rows[1:] if len(normalized_rows) > 1 else []

    if headers and all(not cell for cell in headers):
        headers = [f"col_{idx+1}" for idx in range(len(headers))]
    return headers, body


def _detect_table_title(page_text: str, headers: List[str]) -> Optional[str]:
    candidates = []
    text_lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    for idx, line in enumerate(text_lines):
        if not line.lower().startswith("table"):
            continue
        candidates.append(line.rstrip(":"))
        # look for line immediately after with indicator keywords
        if idx + 1 < len(text_lines):
            next_line = text_lines[idx + 1]
            if any(keyword in next_line.lower() for keyword in TABLE_KEYWORDS):
                candidates.append(next_line.rstrip(":"))
    if candidates:
        return candidates[0]

    joined_headers = " ".join(headers).lower()
    for line in text_lines:
        if all(header.lower() in line.lower() for header in headers if header):
            return line.rstrip(":")
    return None


def _extract_inline_tables(page_text: str, page_number: int) -> List[TableData]:
    rows: List[List[str]] = []
    tables: List[TableData] = []
    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            if rows:
                headers, body = _split_table(rows)
                tables.append(TableData(title=None, headers=headers, rows=body, page=page_number))
                rows = []
            continue
        if "|" in stripped:
            cells = [cell.strip() for cell in stripped.split("|") if cell.strip()]
            if cells:
                rows.append(cells)
                continue
        split_cells = re.split(r"\s{3,}", stripped)
        if len(split_cells) >= 3 and any(cell.strip() for cell in split_cells):
            rows.append([cell.strip() for cell in split_cells])
            continue
        if rows:
            headers, body = _split_table(rows)
            tables.append(TableData(title=None, headers=headers, rows=body, page=page_number))
            rows = []
    if rows:
        headers, body = _split_table(rows)
        tables.append(TableData(title=None, headers=headers, rows=body, page=page_number))
    return tables
