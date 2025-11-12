"""Smart chunking with column awareness and enhanced header/footer detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from medparse.ingest.column_detection import detect_columns, rebuild_lines_with_reading_order
from medparse.ingest.models import PageData
from medparse.text.hash import normalize_paragraph_text, stable_par_hash
from medparse.text.headers import (
    detect_repeating_header_footer,
    is_footer_line,
    is_header_line,
    strip_headers_and_footers,
)


@dataclass(slots=True)
class SmartParagraph:
    """Enhanced paragraph with layout metadata."""

    id: str
    page: int
    text: str
    char_span: Tuple[int, int]
    column_index: Optional[int] = None  # Which column (0, 1, 2...) if multi-column
    is_multi_column: bool = False  # Whether page has multiple columns


def iter_smart_paragraphs(
    pages: Sequence[PageData],
    *,
    use_column_detection: bool = True,
    join_hyphens: bool = True,
    strip_headers: bool = True,
    strip_footers: bool = True,
) -> Iterator[SmartParagraph]:
    """Yield paragraphs with column-aware reading order.

    Args:
        pages: Input pages
        use_column_detection: Enable multi-column layout detection
        join_hyphens: Join hyphenated words across lines
        strip_headers: Remove page headers
        strip_footers: Remove page footers

    Yields:
        Smart paragraphs with correct reading order
    """
    # First pass: detect repeating headers/footers across all pages
    all_page_lines = []
    for page in pages:
        lines = list(page.lines or [])
        if not lines and page.text:
            lines = page.text.splitlines()
        all_page_lines.append(lines)

    repeating_headers, repeating_footers = detect_repeating_header_footer(
        all_page_lines,
        min_occurrences=max(3, len(pages) // 4),  # Require at least 25% occurrence
    )

    # Second pass: process each page with column detection
    for page in pages:
        # Detect columns and get correct reading order
        if use_column_detection and page.blocks:
            layout = detect_columns(page)
            if layout.is_multi_column:
                lines = rebuild_lines_with_reading_order(page, layout)
                column_map = _build_line_column_map(layout)
            else:
                lines = list(page.lines or [])
                column_map = {}
        else:
            lines = list(page.lines or [])
            column_map = {}

        if not lines and page.text:
            lines = page.text.splitlines()

        # Remove repeating headers/footers
        lines = _remove_repeating_patterns(lines, repeating_headers, repeating_footers)

        # Strip first/last line if header/footer
        lines = strip_headers_and_footers(
            lines,
            strip_headers=strip_headers,
            strip_footers=strip_footers,
            aggressive=True,
        )

        if not lines:
            continue

        # Extract paragraphs
        buffer: List[str] = []
        para_count = 0
        current_column: Optional[int] = None

        for line_idx, raw_line in enumerate(lines):
            stripped = raw_line.strip()

            if not stripped:
                # Empty line - flush buffer
                if buffer:
                    text = _flush_buffer(buffer, join_hyphens=join_hyphens)
                    normalized = normalize_paragraph_text(text)
                    if normalized:
                        para_id = f"page{page.number}_para{para_count}"
                        para_count += 1
                        yield SmartParagraph(
                            id=para_id,
                            page=page.number,
                            text=normalized,
                            char_span=(0, len(normalized)),
                            column_index=current_column,
                            is_multi_column=bool(column_map),
                        )
                buffer = []
                current_column = None
                continue

            # Skip boilerplate headers/footers
            if (strip_headers and is_header_line(stripped)) or (strip_footers and is_footer_line(stripped)):
                continue

            # Detect paragraph boundaries
            if buffer:
                # Numbered list item
                if re.match(r"^\d+[\).]", stripped):
                    text = _flush_buffer(buffer, join_hyphens=join_hyphens)
                    normalized = normalize_paragraph_text(text)
                    if normalized:
                        para_id = f"page{page.number}_para{para_count}"
                        para_count += 1
                        yield SmartParagraph(
                            id=para_id,
                            page=page.number,
                            text=normalized,
                            char_span=(0, len(normalized)),
                            column_index=current_column,
                            is_multi_column=bool(column_map),
                        )
                    buffer = []
                    current_column = None

                # ALL CAPS heading (short)
                elif stripped.isupper() and len(stripped.split()) <= 8:
                    text = _flush_buffer(buffer, join_hyphens=join_hyphens)
                    normalized = normalize_paragraph_text(text)
                    if normalized:
                        para_id = f"page{page.number}_para{para_count}"
                        para_count += 1
                        yield SmartParagraph(
                            id=para_id,
                            page=page.number,
                            text=normalized,
                            char_span=(0, len(normalized)),
                            column_index=current_column,
                            is_multi_column=bool(column_map),
                        )
                    buffer = []
                    current_column = None

            # Handle hyphenation
            if buffer and buffer[-1].endswith("-") and join_hyphens:
                buffer[-1] = buffer[-1][:-1] + stripped
            else:
                buffer.append(stripped)

            # Track column
            if line_idx in column_map:
                current_column = column_map[line_idx]

        # Flush remaining buffer
        if buffer:
            text = _flush_buffer(buffer, join_hyphens=join_hyphens)
            normalized = normalize_paragraph_text(text)
            if normalized:
                para_id = f"page{page.number}_para{para_count}"
                yield SmartParagraph(
                    id=para_id,
                    page=page.number,
                    text=normalized,
                    char_span=(0, len(normalized)),
                    column_index=current_column,
                    is_multi_column=bool(column_map),
                )


def build_smart_paragraph_store(
    doc_id: str,
    pages: Sequence[PageData],
    *,
    use_column_detection: bool = True,
    join_hyphens: bool = True,
    strip_headers: bool = True,
    strip_footers: bool = True,
) -> tuple[Dict[str, Dict[str, object]], Dict[str, object]]:
    """Build paragraph store with smart chunking and column awareness.

    Returns:
        Tuple of (paragraph_store, metadata_dict)
    """
    store: Dict[str, Dict[str, object]] = {}
    global_index = 0
    multi_column_pages = 0
    total_columns = 0

    for paragraph in iter_smart_paragraphs(
        pages,
        use_column_detection=use_column_detection,
        join_hyphens=join_hyphens,
        strip_headers=strip_headers,
        strip_footers=strip_footers,
    ):
        hash_id = stable_par_hash(doc_id, paragraph.page, paragraph.text)
        occurrence = {
            "page": paragraph.page,
            "char_span": list(paragraph.char_span),
            "column_index": paragraph.column_index,
        }

        if hash_id not in store:
            store[hash_id] = {
                "id": paragraph.id,
                "text": paragraph.text,
                "page": paragraph.page,
                "char_span": list(paragraph.char_span),
                "length": len(paragraph.text),
                "order": [global_index],
                "occurrences": [occurrence],
                "is_multi_column": paragraph.is_multi_column,
            }
        else:
            # Duplicate paragraph
            occurrences = store[hash_id].setdefault("occurrences", [])
            occurrences.append(occurrence)
            order = store[hash_id].setdefault("order", [])
            order.append(global_index)

        if paragraph.is_multi_column:
            multi_column_pages += 1
        if paragraph.column_index is not None:
            total_columns = max(total_columns, paragraph.column_index + 1)

        global_index += 1

    # Build metadata
    metadata = {
        "total_paragraphs": global_index,
        "unique_paragraphs": len(store),
        "dedup_applied": global_index > len(store),
        "multi_column_pages": multi_column_pages,
        "max_columns_detected": total_columns,
        "used_smart_chunking": use_column_detection,
    }

    # Add pages field to each entry
    for entry in store.values():
        entry.setdefault("pages", [entry.get("page")])

    return store, metadata


def _flush_buffer(buffer: List[str], *, join_hyphens: bool) -> str:
    """Join buffer lines into single paragraph text."""
    if not buffer:
        return ""
    pieces: List[str] = []
    for line in buffer:
        if join_hyphens and pieces and pieces[-1].endswith("-"):
            pieces[-1] = pieces[-1][:-1] + line
        else:
            pieces.append(line)
    return " ".join(pieces)


def _build_line_column_map(layout) -> Dict[int, int]:
    """Build mapping from line index to column index."""
    line_to_column: Dict[int, int] = {}
    line_idx = 0
    for column in layout.columns:
        for block in column.blocks:
            if block.text:
                num_lines = block.text.count("\n") + 1
                for _ in range(num_lines):
                    line_to_column[line_idx] = column.index
                    line_idx += 1
    return line_to_column


def _remove_repeating_patterns(
    lines: List[str],
    repeating_headers: List[str],
    repeating_footers: List[str],
) -> List[str]:
    """Remove lines that match repeating header/footer patterns."""
    cleaned = []
    for line in lines:
        normalized = line.strip()
        if normalized in repeating_headers or normalized in repeating_footers:
            continue
        cleaned.append(line)
    return cleaned


__all__ = [
    "SmartParagraph",
    "iter_smart_paragraphs",
    "build_smart_paragraph_store",
]
