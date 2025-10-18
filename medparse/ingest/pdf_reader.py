"""PDF reading utilities built on PyMuPDF with graceful fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, List, Optional, Sequence, Tuple

from medparse.ingest.cleaning import normalize_text_artifacts

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - library not available
    fitz = None  # type: ignore

try:
    import pdfplumber  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None  # type: ignore


@dataclass(slots=True)
class TextBlock:
    """Normalized text block within a page."""

    text: str
    bbox: Optional[Tuple[float, float, float, float]]
    font_size: Optional[float]
    is_bold: bool


@dataclass(slots=True)
class PageContent:
    """Container for page-level content emitted by the ingestion layer."""

    number: int
    text: str
    lines: List[str]
    blocks: List[TextBlock]
    tables: List[dict]


def _clean_lines(raw: Sequence[str]) -> List[str]:
    cleaned: List[str] = []
    for line in raw:
        if not line:
            continue
        normalised = normalize_text_artifacts(line).strip()
        if normalised:
            cleaned.append(normalised)
    return cleaned


def iter_pages(pdf_path: Path) -> Iterator[PageContent]:
    """Yield ``PageContent`` instances for each page in the PDF.

    The function prefers PyMuPDF for rich layout metadata. If the file lacks a PDF
    structure (common in tests with text fixtures) or PyMuPDF is unavailable, it
    gracefully falls back to treating the file as plain UTF-8 text.
    """

    if fitz is not None:
        try:
            document = fitz.open(pdf_path)  # type: ignore[arg-type]
        except Exception:
            document = None
        else:
            for index, page in enumerate(document, start=1):
                # Collect text blocks with typography metadata
                block_payload: List[TextBlock] = []
                for block in page.get_text("dict").get("blocks", []):
                    if "lines" not in block:
                        continue
                    spans = [
                        span
                        for line in block.get("lines", [])
                        for span in line.get("spans", [])
                        if span.get("text")
                    ]
                    if not spans:
                        continue
                    text = " ".join(span["text"].strip() for span in spans).strip()
                    if not text:
                        continue
                    text = normalize_text_artifacts(text)
                    first_span = spans[0]
                    font_name = first_span.get("font", "")
                    block_payload.append(
                        TextBlock(
                            text=text,
                            bbox=tuple(block.get("bbox", (0.0, 0.0, 0.0, 0.0))),  # type: ignore[arg-type]
                            font_size=first_span.get("size"),
                            is_bold="bold" in font_name.lower(),
                        )
                    )

                page_text = normalize_text_artifacts(page.get_text("text"))
                lines = _clean_lines(page_text.splitlines())
                tables = _extract_tables_with_pdfplumber(pdf_path, index) if pdfplumber else []
                yield PageContent(
                    number=index,
                    text=page_text,
                    lines=lines,
                    blocks=block_payload,
                    tables=tables,
                )
            return

    # Fallback: treat the file as plain text
    raw_bytes = pdf_path.read_bytes()
    text = normalize_text_artifacts(raw_bytes.decode("utf-8", errors="ignore"))
    lines = _clean_lines(text.splitlines())
    blocks = [
        TextBlock(text=line, bbox=None, font_size=None, is_bold=line.isupper()) for line in lines
    ]
    yield PageContent(number=1, text=text, lines=lines, blocks=blocks, tables=[])


def _extract_tables_with_pdfplumber(pdf_path: Path, page_number: int) -> List[dict]:
    """Extract table metadata via pdfplumber for the requested page."""
    if pdfplumber is None:
        return []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_number - 1]
            tables = []
            for table in page.extract_tables():
                if not table:
                    continue
                tables.append(
                    {
                        "rows": table,
                        "page": page_number,
                    }
                )
            return tables
    except Exception:
        return []
