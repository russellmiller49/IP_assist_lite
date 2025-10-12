"""Extractor for book chapter documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from medparse.config import ExtractionConfig
from medparse.ingest.pdf_reader import PageContent, iter_pages
from medparse.types.base import EvidenceSpan
from medparse.types.book import BookChapterDocument, Section


SECTION_ALIASES: Dict[str, str] = {
    "introduction": "Introduction",
    "airway-esophageal fistulas": "Airway-Esophageal Fistulas",
    "etiology and classification": "Etiology and Classification",
    "clinical presentation and symptomatology": "Clinical Presentation and Symptomatology",
    "clinical presentation": "Clinical Presentation",
    "diagnosis": "Diagnosis",
    "management": "Management",
    "prognosis": "Prognosis",
    "conclusion": "Conclusion",
    "adult airway-esophageal fistula management": "Adult airway-esophageal fistula management",
    "esophageal stent": "Esophageal stent",
    "airway stent**": "Airway stent",
    "dual airway-esophageal stenting": "Dual airway-esophageal stenting",
}


def extract_book_chapter(
    pdf_path: Path, config: Optional[ExtractionConfig] = None
) -> BookChapterDocument:
    """Extract book chapter structure."""
    config = config or ExtractionConfig()
    pages = list(iter_pages(pdf_path))
    sections = _extract_sections(pages)

    if not sections:
        fallback_paragraphs = _lines_to_paragraphs(
            [line for page in pages for line in page.lines]
        )
        if fallback_paragraphs:
            sections = [
                Section(
                    title="Content",
                    paragraphs=fallback_paragraphs,
                    evidence=EvidenceSpan(text=fallback_paragraphs[0], page=1),
                )
            ]

    document = BookChapterDocument(
        doc_type="book_chapter",
        source_file=str(pdf_path),
        page_count=len(pages),
        title=_extract_title(pages),
        authors=_extract_authors(pages),
        sections=sections,
    )

    if config.fail_fast and not sections:
        raise ValueError("Book chapter extraction failed to find sections.")

    return document


def _extract_sections(pages: Sequence[PageContent]) -> List[Section]:
    sections: List[Section] = []
    current_title: Optional[str] = None
    current_page = 1
    current_lines: List[str] = []
    seen_titles: set[str] = set()

    for page in pages:
        for raw_line in page.lines:
            line = raw_line.strip()
            if not line or re.search(r"\.{3,}", line):
                continue

            normalized = re.sub(r"^\d+(?:\.\d+)*\s*", "", line.lower())
            canonical = SECTION_ALIASES.get(normalized)
            if canonical:
                if current_title and current_lines:
                    paragraphs = _lines_to_paragraphs(current_lines)
                    if paragraphs and current_title not in seen_titles:
                        sections.append(
                            Section(
                                title=current_title,
                                paragraphs=paragraphs,
                                evidence=EvidenceSpan(text=current_title, page=current_page),
                            )
                        )
                        seen_titles.add(current_title)
                current_title = canonical
                current_page = page.number
                current_lines = []
                continue

            if current_title:
                current_lines.append(line)

    if current_title and current_lines and current_title not in seen_titles:
        paragraphs = _lines_to_paragraphs(current_lines)
        if paragraphs:
            sections.append(
                Section(
                    title=current_title,
                    paragraphs=paragraphs,
                    evidence=EvidenceSpan(text=current_title, page=current_page),
                )
            )

    return sections


def _extract_title(pages: Sequence[PageContent]) -> str:
    if not pages:
        return "Untitled Chapter"
    first_page = pages[0]
    return first_page.lines[0] if first_page.lines else "Untitled Chapter"


def _extract_authors(pages: Sequence[PageContent]) -> List[str]:
    for page in pages:
        for line in page.lines:
            if line.lower().startswith("authors:"):
                return [author.strip() for author in line.split(":", 1)[1].split(",")]
    return []


def _lines_to_paragraphs(lines: List[str]) -> List[str]:
    paragraphs: List[str] = []
    buffer: List[str] = []
    for line in lines:
        if not line:
            continue
        buffer.append(line)
        if line.endswith(('.', '?', '!')) and buffer:
            paragraphs.append(" ".join(buffer))
            buffer = []
    if buffer:
        paragraphs.append(" ".join(buffer))

    cleaned = [re.sub(r"\s+", " ", paragraph).strip() for paragraph in paragraphs]
    cleaned = [text for text in cleaned if len(text.split()) >= 5]
    if not cleaned and lines:
        merged = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if len(merged.split()) >= 5:
            cleaned = [merged]
    return cleaned
