"""Convert tables to markdown format with proper alignment and structure."""

from __future__ import annotations

import re
from typing import List, Literal, Optional, Sequence

ColumnAlignment = Literal["left", "center", "right"]


def _estimate_column_alignment(
    headers: List[str],
    rows: List[List[str]],
    col_idx: int,
) -> ColumnAlignment:
    """Estimate column alignment based on content.

    Heuristics:
    - Numeric columns → right aligned
    - Very short columns (< 5 chars avg) → center
    - Default → left
    """
    values = [headers[col_idx]] if col_idx < len(headers) else []
    for row in rows:
        if col_idx < len(row):
            values.append(row[col_idx])

    if not values:
        return "left"

    # Check if most values are numeric
    numeric_count = 0
    for val in values:
        cleaned = val.strip().replace(",", "").replace("%", "").replace("±", "")
        # Match numbers, ranges, p-values, etc.
        if re.match(r"^[\d\.\-<>≤≥±]+$", cleaned) or re.match(r"^\d+[\.\d]*$", cleaned):
            numeric_count += 1

    if numeric_count / len(values) >= 0.6:
        return "right"

    # Check average length
    avg_len = sum(len(v.strip()) for v in values) / len(values)
    if avg_len < 5:
        return "center"

    return "left"


def _get_column_widths(
    headers: List[str],
    rows: List[List[str]],
    min_width: int = 3,
) -> List[int]:
    """Calculate minimum column widths to fit all content."""
    num_cols = len(headers)
    widths = [len(h) for h in headers]

    for row in rows:
        for col_idx, cell in enumerate(row):
            if col_idx < num_cols:
                widths[col_idx] = max(widths[col_idx], len(cell))

    return [max(w, min_width) for w in widths]


def _format_alignment_row(
    alignments: List[ColumnAlignment],
    widths: List[int],
) -> str:
    """Generate markdown alignment row (e.g., |:---|:---:|---:|)."""
    parts = []
    for align, width in zip(alignments, widths):
        if align == "center":
            parts.append(":" + "-" * (width - 2) + ":")
        elif align == "right":
            parts.append("-" * (width - 1) + ":")
        else:  # left
            parts.append(":" + "-" * (width - 1))
    return "| " + " | ".join(parts) + " |"


def _format_row(
    cells: List[str],
    widths: List[int],
    alignments: List[ColumnAlignment],
) -> str:
    """Format a single table row with proper padding."""
    padded_cells = []
    for idx, (cell, width, align) in enumerate(zip(cells, widths, alignments)):
        # Clean cell content
        cleaned = cell.replace("\n", " ").replace("|", "\\|").strip()

        # Apply padding based on alignment
        if align == "center":
            padded = cleaned.center(width)
        elif align == "right":
            padded = cleaned.rjust(width)
        else:  # left
            padded = cleaned.ljust(width)

        padded_cells.append(padded)

    # Pad remaining columns if row is short
    while len(padded_cells) < len(widths):
        padded_cells.append(" " * widths[len(padded_cells)])

    return "| " + " | ".join(padded_cells) + " |"


def _flatten_multi_row_headers(headers: List[List[str]]) -> List[str]:
    """Flatten multi-row headers into single row.

    For multi-row headers, concatenate with newline or merge intelligently.
    Example:
        [["Patient", "Demographics"], ["Age", "Sex"]]
        → ["Patient\nAge", "Demographics\nSex"]
    """
    if not headers:
        return []

    if len(headers) == 1:
        return headers[0]

    # Find maximum number of columns across all header rows
    max_cols = max(len(row) for row in headers)

    # Pad all rows to same length
    padded_headers = []
    for row in headers:
        padded = row + [""] * (max_cols - len(row))
        padded_headers.append(padded)

    # Combine vertically
    result = []
    for col_idx in range(max_cols):
        parts = [row[col_idx] for row in padded_headers if row[col_idx].strip()]
        result.append(" ".join(parts) if parts else f"col_{col_idx + 1}")

    return result


def table_to_markdown(
    headers: List[List[str]],
    rows: List[List[str]],
    *,
    auto_align: bool = True,
    caption: Optional[str] = None,
    label: Optional[str] = None,
) -> str:
    """Convert table to markdown format.

    Args:
        headers: Multi-row headers (List of header rows)
        rows: Table data rows
        auto_align: Automatically detect column alignment
        caption: Optional table caption
        label: Optional table label

    Returns:
        Markdown-formatted table string

    Example:
        >>> headers = [["Name", "Age", "Score"]]
        >>> rows = [["Alice", "25", "95"], ["Bob", "30", "88"]]
        >>> print(table_to_markdown(headers, rows))
        | Name  | Age | Score |
        |:------|----:|------:|
        | Alice |  25 |    95 |
        | Bob   |  30 |    88 |
    """
    if not headers and not rows:
        return ""

    # Flatten multi-row headers
    flat_headers = _flatten_multi_row_headers(headers) if headers else []

    # If no headers but have rows, generate column names
    if not flat_headers and rows:
        num_cols = max(len(row) for row in rows) if rows else 0
        flat_headers = [f"col_{i+1}" for i in range(num_cols)]

    # Calculate column widths
    widths = _get_column_widths(flat_headers, rows)

    # Determine alignments
    alignments: List[ColumnAlignment] = []
    if auto_align:
        for col_idx in range(len(flat_headers)):
            alignments.append(_estimate_column_alignment(flat_headers, rows, col_idx))
    else:
        alignments = ["left"] * len(flat_headers)

    # Build markdown
    lines = []

    # Add label if present
    if label:
        lines.append(f"**{label}**")
        lines.append("")

    # Header row
    lines.append(_format_row(flat_headers, widths, alignments))

    # Alignment row
    lines.append(_format_alignment_row(alignments, widths))

    # Data rows
    for row in rows:
        lines.append(_format_row(row, widths, alignments))

    # Caption
    if caption:
        lines.append("")
        lines.append(f"*{caption}*")

    return "\n".join(lines)


def detect_stub_column(
    headers: List[str],
    rows: List[List[str]],
) -> Optional[int]:
    """Detect if first column is a stub (row header) column.

    Heuristics:
    - First column has mostly text
    - Other columns have mostly numbers
    - First column values are unique or categories
    """
    if not rows or not headers:
        return None

    if len(headers) < 2:
        return None

    # Get first column values
    first_col_values = [row[0] for row in rows if row]

    if not first_col_values:
        return None

    # Check uniqueness (stub columns often have unique values)
    uniqueness_ratio = len(set(first_col_values)) / len(first_col_values)

    # Check if first column is mostly text
    text_count = sum(
        1 for val in first_col_values
        if not re.match(r"^[\d\.\-<>≤≥±,% ]+$", val.strip())
    )
    text_ratio = text_count / len(first_col_values)

    # Check if other columns are mostly numeric
    numeric_count = 0
    total_other_cells = 0
    for row in rows:
        for idx, cell in enumerate(row[1:], start=1):
            total_other_cells += 1
            cleaned = cell.strip().replace(",", "").replace("%", "")
            if re.match(r"^[\d\.\-<>≤≥±]+$", cleaned):
                numeric_count += 1

    numeric_ratio = numeric_count / total_other_cells if total_other_cells > 0 else 0

    # Decision: likely stub column if:
    # - High text ratio in first column (>60%)
    # - High numeric ratio in other columns (>40%)
    # - OR high uniqueness (>80%)
    if (text_ratio > 0.6 and numeric_ratio > 0.4) or uniqueness_ratio > 0.8:
        return 0

    return None


__all__ = [
    "table_to_markdown",
    "detect_stub_column",
    "ColumnAlignment",
]
