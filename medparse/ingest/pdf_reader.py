"""PDF reading utilities with engine fallbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple

from medparse.ingest.cleaning import normalize_text_artifacts
from medparse.ingest.models import Heading, PageData, TextBlock, WordBox
from medparse.ingest.tables import extract_tables
from medparse.normalize.text_assemble import words_to_text, restore_spaces

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - library not available
    fitz = None  # type: ignore

try:
    import pdfplumber  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None  # type: ignore


def _clean_lines(raw: Sequence[str]) -> List[str]:
    cleaned: List[str] = []
    for line in raw:
        if not line:
            continue
        normalised = normalize_text_artifacts(line).strip()
        if normalised:
            cleaned.append(normalised)
    return cleaned


def iter_pages(
    pdf_path: Path,
    *,
    include_headings: bool = True,
    engine: str = "pymupdf",
    page_limit: Optional[int] = None,
) -> Iterator[PageData]:
    """Yield ``PageData`` instances for each page in the PDF.

    Prefers PyMuPDF for full layout metadata and falls back to treating the file
    as UTF-8 text when PyMuPDF cannot load the document (helpful for fixtures).
    """

    engine_normalized = (engine or "pymupdf").lower()

    if engine_normalized == "pdfplumber" and pdfplumber is not None:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                limit = page_limit or total_pages
                for index in range(total_pages):
                    if limit and index + 1 > limit:
                        break
                    page = pdf.pages[index]

                    # Extract words for proper spacing
                    try:
                        words_raw = page.extract_words(
                            x_tolerance=1.0,
                            y_tolerance=1.0,
                            keep_blank_chars=False
                        )
                        word_boxes: List[WordBox] = [
                            (w["x0"], w["top"], w["x1"], w["bottom"], w["text"])
                            for w in words_raw
                        ]
                        # Build text from words with proper spacing
                        page_text = restore_spaces(words_to_text(word_boxes))
                    except Exception:
                        # Fallback to raw text extraction
                        page_text = page.extract_text() or ""
                        word_boxes = []

                    page_text = normalize_text_artifacts(page_text)
                    lines = _clean_lines(page_text.splitlines())
                    blocks = [
                        TextBlock(text=line, bbox=None, font_size=None, is_bold=line.isupper())
                        for line in lines
                    ]
                    tables = extract_tables(pdf_path, index + 1, page_text)
                    page_data = PageData(
                        number=index + 1,
                        text=page_text,
                        lines=lines,
                        blocks=blocks,
                        tables=tables,
                        word_boxes=word_boxes,
                    )
                    if include_headings:
                        page_data.headings = _detect_page_headings(page_data)
                    yield page_data
                return
        except Exception:
            # Fall back to PyMuPDF/text-only path when pdfplumber fails
            pass

    if fitz is not None:
        try:
            document = fitz.open(pdf_path)  # type: ignore[arg-type]
        except Exception:
            document = None
        else:
            for index, page in enumerate(document, start=1):
                if page_limit and index > page_limit:
                    break
                page_data = _page_from_pymupdf(pdf_path, page, index)
                if include_headings:
                    page_data.headings = _detect_page_headings(page_data)
                yield page_data
            return

    # Fallback: treat local file bytes as text (used in tests)
    raw_bytes = pdf_path.read_bytes()
    text = normalize_text_artifacts(raw_bytes.decode("utf-8", errors="ignore"))
    lines = _clean_lines(text.splitlines())
    blocks = [
        TextBlock(text=line, bbox=None, font_size=None, is_bold=line.isupper()) for line in lines
    ]
    tables = extract_tables(pdf_path, 1, text)
    page_data = PageData(number=1, text=text, lines=lines, blocks=blocks, tables=tables)
    if include_headings:
        page_data.headings = _detect_page_headings(page_data)
    yield page_data


def _page_from_pymupdf(pdf_path: Path, page: "fitz.Page", index: int) -> PageData:
    block_payload: List[TextBlock] = []
    for block in page.get_text("dict").get("blocks", []):
        spans = _collect_spans(block)
        if not spans:
            continue
        text = " ".join(span["text"].strip() for span in spans).strip()
        if not text:
            continue
        text = normalize_text_artifacts(text)
        first_span = spans[0]
        block_payload.append(
            TextBlock(
                text=text,
                bbox=_as_tuple(block.get("bbox")),
                font_size=first_span.get("size"),
                is_bold="bold" in (first_span.get("font") or "").lower(),
            )
        )

    # Extract words for spacing restoration
    try:
        words_raw = page.get_text("words")  # Returns list of (x0, y0, x1, y1, "word", block_no, line_no, word_no)
        word_boxes: List[WordBox] = [
            (w[0], w[1], w[2], w[3], w[4])
            for w in words_raw
            if len(w) >= 5 and w[4].strip()
        ]
        page_text = restore_spaces(words_to_text(word_boxes))
    except Exception:
        page_text = page.get_text("text")
        word_boxes = []

    page_text = normalize_text_artifacts(page_text)
    lines = _clean_lines(page_text.splitlines())
    tables = extract_tables(pdf_path, index, page_text)
    return PageData(
        number=index,
        text=page_text,
        lines=lines,
        blocks=block_payload,
        tables=tables,
        word_boxes=word_boxes
    )


def _collect_spans(block: dict) -> List[dict]:
    spans: List[dict] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = span.get("text", "")
            if text and text.strip():
                spans.append(span)
    return spans


def _as_tuple(bbox: Optional[Sequence[float]]) -> Optional[Tuple[float, float, float, float]]:
    if not bbox:
        return None
    coords = tuple(float(value) for value in bbox[:4])
    if len(coords) != 4:
        return None
    return coords


def _detect_page_headings(page: PageData) -> List[Heading]:
    from medparse.ingest.layout import detect_headings  # Lazy import to avoid cycles

    return detect_headings(page)
