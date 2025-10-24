"""Textbook chapter extraction pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from medparse.extract.utils import iter_section_windows, load_pages, section_text_between
from medparse.ingest.models import PageData
from medparse.normalize.metadata import normalize_authors, normalize_chapter_title
from medparse.schema.common import EvidenceSpan
from medparse.schema.textbook import BookMeta, Section, TextbookChapterDocument
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)
BOOK_META_FILENAMES = ("book_meta.yaml", "book_meta.yml", "book_meta.json")


def extract_textbook_chapter(
    pdf_path: Path,
    *,
    engine: str = "pymupdf",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
) -> TextbookChapterDocument:
    """Extract structured data for a single textbook chapter PDF."""

    pages = pages or load_pages(pdf_path, engine=engine, max_pages=page_limit)
    headings = [heading for page in pages for heading in page.headings if heading.level == 1]
    primary_heading = headings[0] if headings else None
    raw_title = primary_heading.title if primary_heading else (pages[0].lines[0] if pages and pages[0].lines else pdf_path.stem)
    chapter_title, chapter_number = normalize_chapter_title(raw_title)

    authors = _extract_authors(pages)
    sections: List[Section] = []
    keywords: List[str] = []
    abstract: Optional[str] = None
    for heading, next_heading in iter_section_windows(pages):
        section_lower = heading.title.lower()
        text, evidence, fragments = section_text_between(pages, heading, next_heading)
        paragraphs = _paragraphs_from_lines(fragments)
        section = Section(title=heading.title, paragraphs=paragraphs, evidence=evidence)
        if section_lower == "abstract":
            abstract = text
        elif section_lower == "keywords":
            keywords = [token.strip() for token in text.split(",") if token.strip()]
        else:
            sections.append(section)

    book_meta = _load_book_metadata(pdf_path.parent)

    document = TextbookChapterDocument(
        doc_type="textbook_chapter",
        source_file=str(pdf_path),
        page_count=len(pages),
        chapter_title=chapter_title,
        chapter_number=chapter_number,
        authors=authors,
        abstract=abstract,
        keywords=keywords,
        sections=sections,
        book_meta=book_meta,
    )
    return document


def _extract_authors(pages: Sequence) -> List[str]:
    if not pages:
        return []
    top_lines = pages[0].lines[:10]
    for line in top_lines[1:]:
        if any(char.isalpha() for char in line) and "," in line:
            return normalize_authors([line])
    return []


def _paragraphs_from_lines(lines: List[str]) -> List[str]:
    paragraphs: List[str] = []
    buffer: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            continue
        buffer.append(stripped)
    if buffer:
        paragraphs.append(" ".join(buffer))
    return paragraphs


def _load_book_metadata(folder: Path) -> Optional[BookMeta]:
    # Look for metadata in the folder first
    for filename in BOOK_META_FILENAMES:
        candidate = folder / filename
        if candidate.exists():
            data = _read_meta_file(candidate)
            if not data:
                LOGGER.warning("Failed to parse book metadata file: %s", candidate)
                return None
            try:
                if "year" in data and isinstance(data["year"], str) and data["year"].isdigit():
                    data["year"] = int(data["year"])
                return BookMeta(**data)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Invalid book metadata in %s: %s", candidate, exc)
                return None
    
    # If not found, look in pdf subdirectory
    pdf_subdir = folder / "pdf"
    if pdf_subdir.exists():
        for filename in BOOK_META_FILENAMES:
            candidate = pdf_subdir / filename
            if candidate.exists():
                data = _read_meta_file(candidate)
                if not data:
                    LOGGER.warning("Failed to parse book metadata file: %s", candidate)
                    return None
                try:
                    if "year" in data and isinstance(data["year"], str) and data["year"].isdigit():
                        data["year"] = int(data["year"])
                    return BookMeta(**data)
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.warning("Invalid book metadata in %s: %s", candidate, exc)
                    return None
    
    LOGGER.warning("No book_meta file found in %s", folder)
    return None


def _read_meta_file(path: Path) -> Dict[str, object] | None:
    if path.suffix.lower() == ".json":
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover - fallback parser
        return _parse_simple_yaml(path.read_text(encoding="utf-8"))

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def _parse_simple_yaml(text: str) -> Dict[str, object]:
    data: Dict[str, object] = {}
    current_key: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- ") and current_key:
            data.setdefault(current_key, [])
            assert isinstance(data[current_key], list)
            data[current_key].append(line[2:].strip().strip('"'))
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"')
            if value:
                data[key] = value
                current_key = None
            else:
                data[key] = []
                current_key = key
    return data


__all__ = ["extract_textbook_chapter"]
