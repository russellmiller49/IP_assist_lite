"""Normalizer for IFU tables (allowlist, merge, dedupe)."""

from __future__ import annotations

import re
from typing import Dict, List

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


__all__ = ["clean_tables"]
