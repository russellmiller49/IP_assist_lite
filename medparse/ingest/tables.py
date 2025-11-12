"""Table extraction helpers using pdfplumber heuristics."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from medparse.ingest.models import TableData

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

try:
    import pdfplumber  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None  # type: ignore


def extract_tables(pdf_path: Path, page_number: int, page_text: str) -> List[TableData]:
    """Extract tables for a page using pdfplumber."""

    if pdfplumber is None:
        # Fallback to inline table extraction only if pdfplumber not available
        lower_text = page_text.lower()
        if any(keyword in lower_text for keyword in TABLE_KEYWORDS):
            return _extract_inline_tables(page_text, page_number)
        return []

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
        if rows:
            headers, body = _split_table(rows)
            tables.append(TableData(title=None, headers=headers, rows=body, page=page_number))
            rows = []
    if rows:
        headers, body = _split_table(rows)
        tables.append(TableData(title=None, headers=headers, rows=body, page=page_number))
    return tables
