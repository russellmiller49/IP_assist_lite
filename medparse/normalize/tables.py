"""Normalizer for IFU tables (allowlist, merge, dedupe) and paragraph ghost suppression."""

from __future__ import annotations

import re
from typing import Dict, List, Set

# Allowlist for key IFU tables (component specs, power, LEDs, compatibility, sterilization, etc.)
ALLOW_PREFIXES = [
    # Ion manual specific
    "table 4.2 led status",
    "table 7.1 power modes",
    "table 6.1 system power",
    "table 6.2 input connections",
    "table b.1 sterilization",
    "table c.1 third-party compatibility",
    "table d.3 power specifications",
    "table d.5 environmental conditions",
    "table f.1 symbols",
    "table g.1 glossary",
    # IEC standards
    "table 1: iec60601-1-2",
    "table 2: iec60601-1-2",
    "table 3: iec60601-1-2",
    # Generic patterns (lowercase for matching)
    "led",
    "power",
    "input",
    "sterilization",
    "compatibility",
    "specifications",
    "environmental",
    "symbols",
    "glossary",
    "part number",
    "components",
]

CONT_RE = re.compile(r"\(continued\)", re.IGNORECASE)
MIN_DATA_ROWS = 2  # Minimum rows to consider a table valid


def normalize_title(title: str | None) -> str:
    return (title or "").strip().lower()


def _is_allowed(title: str | None, rows: List[List[str]]) -> bool:
    """Check if table is allowed based on title patterns and row count."""
    normalized = normalize_title(title)

    # Check explicit prefix matches
    if any(prefix in normalized for prefix in ALLOW_PREFIXES):
        return True

    # Reject if < MIN_DATA_ROWS
    if len(rows) < MIN_DATA_ROWS:
        return False

    # Reject if title looks like a page header (e.g., "Chapter 3")
    if not title or len(title.strip()) < 5:
        return False

    return True


def clean_tables(tables: List[Dict[str, object]] | None) -> List[Dict[str, object]]:
    """Clean IFU tables: merge (continued), dedupe, allowlist, prune empties.

    Steps:
        1. Filter out non-dict or malformed entries
        2. Merge "(continued)" tables with their parents
        3. Deduplicate by normalized title (keep longest)
        4. Apply allowlist and minimum row count filters

    Returns:
        List of cleaned table dictionaries
    """
    if not tables:
        return []

    # Step 1: Filter malformed tables
    filtered = [t for t in tables if isinstance(t, dict)]
    filtered = [t for t in filtered if t.get("title") or any(t.get("rows") or [])]

    # Step 2: Merge "(continued)" tables
    merged: List[Dict[str, object]] = []
    last_by_base: Dict[str, Dict[str, object]] = {}

    for table in filtered:
        title = str(table.get("title") or "").strip()
        base_title = CONT_RE.sub("", title).strip()

        # If this is a continuation, merge rows into parent
        if CONT_RE.search(title) and base_title in last_by_base:
            parent = last_by_base[base_title]
            parent.setdefault("rows", [])
            parent_rows = parent["rows"]
            if not isinstance(parent_rows, list):
                parent_rows = []
                parent["rows"] = parent_rows
            parent_rows.extend(table.get("rows", []) or [])
            continue

        # Otherwise, create new table entry
        new_table = {
            "title": title,
            "headers": list(table.get("headers") or []),
            "rows": [list(row) for row in (table.get("rows") or [])],
            "page": table.get("page"),
            "caption": table.get("caption"),
            "footnotes": list(table.get("footnotes") or []),
            "heading_path": list(table.get("heading_path") or []),
            "rows_truncated": bool(table.get("rows_truncated")),
        }
        merged.append(new_table)
        last_by_base[base_title or title] = new_table

    # Step 3: Deduplicate by title (keep table with most rows)
    dedup_map: Dict[str, Dict[str, object]] = {}
    for table in merged:
        title = table.get("title")
        rows = table.get("rows") or []

        # Apply allowlist filter
        if not _is_allowed(title, rows):
            continue

        title_key = normalize_title(title)
        existing = dedup_map.get(title_key)

        if existing:
            existing_rows = len(existing.get("rows") or [])
            if len(rows) > existing_rows:
                dedup_map[title_key] = table
        else:
            dedup_map[title_key] = table

    return list(dedup_map.values())


def suppress_table_ghosts(
    paragraph_store: Dict[str, Dict[str, object]] | None,
    tables: List[Dict[str, object]] | None,
    *,
    min_len: int = 25,
) -> int:
    """Remove paragraph_store entries that duplicate structured tables on the same page.

    Returns number of paragraph entries removed.
    """
    if not paragraph_store or not isinstance(paragraph_store, dict) or not tables:
        return 0

    def _norm(value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip().lower()

    table_strings_by_page: Dict[int, List[str]] = {}
    for tbl in tables:
        if not isinstance(tbl, dict):
            continue
        page = tbl.get("page")
        if page is None:
            continue
        parts: List[str] = []
        for field in ("title", "caption"):
            if tbl.get(field):
                parts.append(_norm(str(tbl[field])))
        for header in tbl.get("headers") or []:
            if isinstance(header, list):
                parts.extend(_norm(str(h)) for h in header if h)
            else:
                parts.append(_norm(str(header)))
        for row in tbl.get("rows") or []:
            if isinstance(row, list):
                row_text = _norm(" ".join(str(cell) for cell in row if cell is not None))
                if row_text:
                    parts.append(row_text)
            else:
                norm_row = _norm(str(row))
                if norm_row:
                    parts.append(norm_row)
        if parts:
            table_strings_by_page.setdefault(int(page), []).extend([p for p in parts if p])

    removed = 0
    for key, entry in list(paragraph_store.items()):
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        if len(text) < min_len:
            continue
        page = entry.get("page")
        if page is None:
            continue
        candidates = table_strings_by_page.get(int(page))
        if not candidates:
            continue
        norm_par = _norm(text)
        if not norm_par:
            continue
        for tbl_text in candidates:
            if len(tbl_text) < min_len:
                continue
            if norm_par in tbl_text or tbl_text in norm_par:
                paragraph_store.pop(key, None)
                removed += 1
                break

    return removed


def detect_complex_tables(
    tables: List[Dict[str, object]] | None,
    *,
    max_columns: int = 6,
    min_header_fragments: int = 4,
    long_row_threshold: int = 45,
) -> Set[int]:
    """Detect pages with complex tables that should be routed to a vision extractor.

    Heuristics:
      - Many columns (>= max_columns)
      - Fragmented headers (>= min_header_fragments short header tokens)
      - Very long tables (rows >= long_row_threshold)
      - Truncated rows flagged by extractor
    """
    if not tables:
        return set()

    complex_pages: Set[int] = set()

    for tbl in tables:
        if not isinstance(tbl, dict):
            continue
        page = tbl.get("page")
        try:
            page_num = int(page) if page is not None else None
        except (TypeError, ValueError):
            page_num = None

        rows = tbl.get("rows") or []
        headers = tbl.get("headers") or []
        flat_headers: List[str] = []
        if isinstance(headers, list):
            for header in headers:
                if isinstance(header, list):
                    flat_headers.extend(str(h) for h in header if h)
                elif header:
                    flat_headers.append(str(header))

        max_cols = 0
        for row in rows:
            if isinstance(row, list):
                max_cols = max(max_cols, len(row))

        short_header_frags = sum(1 for h in flat_headers if len(str(h).strip()) <= 3)

        is_complex = (
            max_cols >= max_columns
            or short_header_frags >= min_header_fragments
            or len(rows) >= long_row_threshold
            or bool(tbl.get("rows_truncated"))
        )

        if is_complex and page_num is not None:
            complex_pages.add(page_num)

    return complex_pages


__all__ = ["clean_tables", "suppress_table_ghosts", "detect_complex_tables"]
