"""Table extraction helpers using lightweight heuristics."""

from __future__ import annotations

from typing import Dict, Iterable, List


def extract_inline_tables(lines: Iterable[str]) -> List[Dict[str, List[str]]]:
    """Extract simple pipe- or comma-delimited tables from textual lines.

    This provides a deterministic fallback for unit tests where PDFs are represented
    by text fixtures. A more sophisticated implementation can layer in pdfplumber.
    """

    tables: List[Dict[str, List[str]]] = []
    current: List[List[str]] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                tables.append(_table_from_rows(current))
                current = []
            continue

        if "|" in stripped:
            cells = [cell.strip() for cell in stripped.split("|")]
        elif "," in stripped and all(len(part.strip()) > 0 for part in stripped.split(",")):
            cells = [cell.strip() for cell in stripped.split(",")]
        else:
            if current:
                tables.append(_table_from_rows(current))
                current = []
            continue

        current.append(cells)

    if current:
        tables.append(_table_from_rows(current))

    return tables


def _table_from_rows(rows: List[List[str]]) -> Dict[str, List[str]]:
    headers = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    return {"headers": headers, "rows": body}
