"""Shared extractor helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from medparse.ingest.models import Heading, PageData
from medparse.ingest.pdf_reader import iter_pages
from medparse.schema.common import EvidenceSpan


def load_pages(
    pdf_path: Path,
    *,
    engine: str = "pymupdf",
    max_pages: Optional[int] = None,
    ocr: bool = False,
    start_page: int = 1,
    text_normalization: bool = True,
) -> List[PageData]:
    """Load all pages for ``pdf_path`` via the ingestion layer."""

    start_page = max(1, int(start_page or 1))
    return list(
        iter_pages(
            pdf_path,
            engine=engine,
            page_limit=max_pages,
            enable_ocr=ocr,
            start_page=start_page,
            text_normalization=text_normalization,
        )
    )


def iter_section_windows(pages: Sequence[PageData]) -> Iterator[Tuple[Heading, Optional[Heading]]]:
    """Yield `(current_heading, next_heading)` pairs for section extraction."""

    headings: List[Heading] = []
    for page in pages:
        headings.extend([heading for heading in page.headings if heading.kind == "section"])
    headings.sort(key=lambda h: (h.page, h.line_index))

    for idx, current in enumerate(headings):
        nxt = headings[idx + 1] if idx + 1 < len(headings) else None
        yield current, nxt


def section_text_between(
    pages: Sequence[PageData], current: Heading, next_heading: Optional[Heading]
) -> Tuple[str, EvidenceSpan, List[str]]:
    """Collect text residing between ``current`` and ``next_heading``."""

    fragments: List[str] = []
    for page in pages:
        if page.number < current.page:
            continue
        if next_heading and page.number > next_heading.page:
            break

        start_line = 0
        end_line = len(page.lines)
        if page.number == current.page:
            start_line = current.line_index + 1
        if next_heading and page.number == next_heading.page:
            end_line = max(next_heading.line_index, 0)

        if start_line >= end_line:
            continue

        fragments.extend(page.lines[start_line:end_line])

    text = " ".join(fragment.strip() for fragment in fragments if fragment.strip())
    snippet = text[:280] if text else ""
    evidence = EvidenceSpan(text=snippet, page=current.page, bbox=None, confidence=1.0)
    return text, evidence, fragments


def collect_lines(pages: Sequence[PageData]) -> List[str]:
    """Flatten page lines into a single list."""

    lines: List[str] = []
    for page in pages:
        lines.extend(page.lines)
    return lines


def collect_tables(pages: Sequence[PageData]) -> List[dict]:
    """Flatten tables into JSON-serialisable dicts."""

    serialised: List[dict] = []
    for page in pages:
        for table in page.tables:
            serialised.append(
                {
                    "title": table.title,
                    "headers": table.headers,
                    "rows": table.rows,
                    "page": page.number,
                    "caption": table.caption,
                    "footnotes": list(getattr(table, "footnotes", [])),
                    "heading_path": list(getattr(table, "heading_path", [])),
                    "rows_truncated": bool(getattr(table, "rows_truncated", False)),
                }
            )
    return serialised


def reference_section(lines: Sequence[str]) -> List[str]:
    """Return lines belonging to the references section."""

    refs_started = False
    collected: List[str] = []
    for line in lines:
        lowered = line.lower()
        if "references" in lowered or "bibliography" in lowered:
            refs_started = True
            continue
        if refs_started:
            if not line.strip():
                continue
            collected.append(line.strip())
    return collected


__all__ = [
    "load_pages",
    "iter_section_windows",
    "section_text_between",
    "collect_lines",
    "collect_tables",
    "reference_section",
]
