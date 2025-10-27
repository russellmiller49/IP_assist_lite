"""Textbook chapter extractor with profile-aware enrichments."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

from medparse.config import ExtractionConfig, get_extraction_config
from medparse.extract.utils import load_pages
from medparse.ingest.book_meta import load_book_metadata
from medparse.ingest.models import PageData
from medparse.normalize.article_frontmatter import extract_authors_affiliations
from medparse.normalize.metadata import normalize_chapter_title
from medparse.normalize.page_furniture import strip_furniture
from medparse.normalize.textbook_anchors import build_section_map, extract_keywords_clean
from medparse.normalize.figures_captions import FigureBlock, extract_figures_and_captions
from medparse.schema.textbook import (
    AuthorInfo,
    BookMeta,
    FigureInfo,
    SectionMetadata,
    TextbookChapterDocument,
)
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)


def extract_textbook_chapter(
    pdf_path: Path,
    *,
    engine: str = "fitz",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
    config: Optional[ExtractionConfig] = None,
) -> TextbookChapterDocument:
    """Extract structured textbook chapter content."""

    extraction_config = config or get_extraction_config()
    pages = pages or load_pages(pdf_path, engine=engine, max_pages=page_limit)
    if not pages:
        raise ValueError(f"No pages extracted from {pdf_path}")

    _strip_page_furniture(pages)

    title, number = _derive_chapter_title(pages, pdf_path)
    section_map = build_section_map(pages)
    sections = _build_sections(section_map)

    frontmatter = extract_authors_affiliations(pages)
    authors = _build_authors(frontmatter)
    corresponding = _build_corresponding_author(frontmatter)

    keywords = extract_keywords_clean(pages)
    figures = _maybe_extract_figures(pages, extraction_config)

    book_meta_payload = load_book_metadata(pdf_path.parent)
    if book_meta_payload:
        try:
            book_meta = BookMeta.model_validate(book_meta_payload)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Invalid book metadata for %s: %s", pdf_path, exc)
            book_meta = None
    else:
        book_meta = None

    document = TextbookChapterDocument(
        source_file=str(pdf_path),
        page_count=len(pages),
        chapter_title=title,
        chapter_number=number,
        chapter_authors=authors,
        corresponding_author=corresponding,
        keywords=keywords,
        sections=sections,
        figures=_map_figures(figures),
        book_meta=book_meta,
    )
    return document


def _strip_page_furniture(pages: Sequence[PageData]) -> None:
    lines_by_page = [list(page.lines) for page in pages]
    cleaned = strip_furniture(lines_by_page, threshold=0.6)
    for page, clean_lines in zip(pages, cleaned, strict=False):
        page.lines = clean_lines
        page.text = "\n".join(clean_lines)


def _derive_chapter_title(pages: Sequence[PageData], pdf_path: Path) -> tuple[str, Optional[str]]:
    if pages and pages[0].lines:
        first_line = pages[0].lines[0]
        if first_line.lower().startswith("chapter"):
            raw = first_line
        elif pages[0].headings:
            raw = pages[0].headings[0].title
        else:
            raw = first_line
    elif pages and pages[0].headings:
        raw = pages[0].headings[0].title
    else:
        raw = pdf_path.stem
    title, number = normalize_chapter_title(raw)
    return title or raw, number


def _build_sections(raw_sections: Dict[str, Dict[str, object]]) -> Dict[str, SectionMetadata]:
    sections: Dict[str, SectionMetadata] = {}
    for key, payload in raw_sections.items():
        try:
            sections[key] = SectionMetadata(
                text=payload.get("text", ""),
                start_page=payload.get("start_page"),
                end_page=payload.get("end_page"),
                number=payload.get("number"),
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Skipping section %s due to validation error: %s", key, exc)
    return sections


def _build_authors(frontmatter: dict) -> List[AuthorInfo]:
    authors: List[AuthorInfo] = []
    for author in frontmatter.get("authors", []):
        name = " ".join(part for part in (author.get("given"), author.get("family")) if part)
        if not name.strip():
            continue
        authors.append(
            AuthorInfo(
                name=name.strip(),
                email=None,
            )
        )
    return authors


def _build_corresponding_author(frontmatter: dict) -> Optional[AuthorInfo]:
    corr = frontmatter.get("corresponding_author") or {}
    name = corr.get("name")
    if not name:
        return None
    return AuthorInfo(name=name, email=corr.get("email"))


def _maybe_extract_figures(
    pages: Sequence[PageData],
    config: ExtractionConfig,
) -> List[FigureBlock]:
    if not config.is_enriched():
        return []
    return extract_figures_and_captions(list(pages))


def _map_figures(figures: Sequence[FigureBlock]) -> List[FigureInfo]:
    mapped: List[FigureInfo] = []
    for figure in figures:
        mapped.append(
            FigureInfo(
                label=figure.label,
                caption=figure.caption,
                page=figure.page,
            )
        )
    return mapped


__all__ = ["extract_textbook_chapter"]
