"""Textbook chapter extractor with profile-aware enrichments."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

from medparse.config import ExtractionConfig, get_extraction_config
from medparse.extract.utils import load_pages
from medparse.ingest.book_meta import load_book_metadata
from medparse.ingest.models import PageData
from medparse.normalize.article_frontmatter import extract_authors_affiliations
from medparse.normalize.fm_zotero import link_front_matter
from medparse.normalize.layout import is_toc_page
from medparse.normalize.metadata import normalize_chapter_title
from medparse.normalize.page_furniture import strip_furniture
from medparse.normalize.relations import RelationRecord, build_cooccurrence
from medparse.normalize.textbook_anchors import build_section_map, extract_keywords_clean
from medparse.normalize.figures_captions import FigureBlock, extract_figures_and_captions
from medparse.normalize.umls_linking import (
    UmlsEntity as UmlsEntityRecord,
    UmlsLinkingResult,
    link_entities,
)
from medparse.schema.common import Relation, UmlsEntity
from medparse.schema.textbook import (
    AuthorInfo,
    BookMeta,
    FigureInfo,
    SectionMetadata,
    TextbookChapterDocument,
)
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)
UMLS_PAGE_CACHE: Dict[str, List[UmlsEntityRecord]] = {}


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

    umls_result = UmlsLinkingResult(status="skipped_disabled", entities=[])
    umls_records: List[UmlsEntityRecord] = []
    relation_records: List[RelationRecord] = []
    if extraction_config.should_enrich_umls():
        try:
            umls_result = link_entities(pages, cache=UMLS_PAGE_CACHE, enabled=True)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("UMLS linking failed for textbook %s: %s", pdf_path.name, exc)
            umls_result = UmlsLinkingResult(status="skipped_model_missing", entities=[])
        umls_records = umls_result.entities
    if extraction_config.should_extract_relations() and umls_records:
        relation_records = build_cooccurrence(
            [record.model_dump() for record in umls_records],
            window=extraction_config.relation_window or "page",
        )

    book_meta_payload = load_book_metadata(pdf_path.parent)
    if book_meta_payload:
        try:
            # Map JSON fields to schema fields
            normalized_payload = {
                "book_title": book_meta_payload.get("book_title", ""),
                "edition": book_meta_payload.get("edition", ""),
                "publisher": book_meta_payload.get("publisher"),
                "isbn": book_meta_payload.get("isbn", ""),
                "year": book_meta_payload.get("year") or _extract_year(book_meta_payload.get("publication_year")),
                "book_doi": book_meta_payload.get("book_doi") or book_meta_payload.get("doi"),
                "editors": book_meta_payload.get("editors", []) or book_meta_payload.get("editors_or_authors", []),
            }
            book_meta = BookMeta.model_validate(normalized_payload)
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
        umls_entities=_map_umls_entities(umls_records),
        relations=_map_relations(relation_records),
        coverage_ratio=_compute_coverage_ratio(pages, sections),
        book_meta=book_meta,
    )
    fm_info = None
    if extraction_config.should_use_zotero():
        zotero_path = extraction_config.metadata_sources.get("zotero_json")
        try:
            document, fm_info = link_front_matter(
                document,
                zotero_path,
                extraction_config.enrichment,
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Zotero linking failed for textbook %s: %s", pdf_path.name, exc)
            fm_info = {"status": "error", "detail": str(exc), "source": "zotero"}
    document.pipeline_info["umls_status"] = umls_result.status
    document.pipeline_info["umls_entities_count"] = len(umls_records)
    if fm_info:
        document.pipeline_info["front_matter"] = fm_info
    if extraction_config.relation_window:
        document.pipeline_info["relation_window"] = extraction_config.relation_window
    if extraction_config.max_entities:
        document.pipeline_info["max_entities"] = extraction_config.max_entities
    if extraction_config.max_relations:
        document.pipeline_info["max_relations"] = extraction_config.max_relations
    return document


def _strip_page_furniture(pages: Sequence[PageData]) -> None:
    lines_by_page = [list(page.lines) for page in pages]
    cleaned = strip_furniture(lines_by_page, threshold=0.6)
    for page, clean_lines in zip(pages, cleaned, strict=False):
        page.lines = clean_lines
        page.text = "\n".join(clean_lines)


def _extract_year(value: Optional[str]) -> Optional[int]:
    """Extract year as integer from string."""
    if not value:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, AttributeError):
        return None


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


def _map_umls_entities(records: Sequence[UmlsEntityRecord]) -> List[UmlsEntity]:
    mapped: List[UmlsEntity] = []
    for record in records:
        mapped.append(
            UmlsEntity(
                cui=record.cui,
                preferred_term=record.preferred_term,
                semtypes=record.semtypes,
                offsets=record.offsets,
                text=record.text,
                page=record.page,
                confidence=record.confidence,
            )
        )
    return mapped


def _map_relations(records: Sequence[RelationRecord]) -> List[Relation]:
    mapped: List[Relation] = []
    for record in records:
        mapped.append(
            Relation(
                subject=record.subject,
                predicate=record.predicate,
                object=record.object,
                attributes=record.attributes,
            )
        )
    return mapped


def _compute_coverage_ratio(
    pages: Sequence[PageData],
    sections: Dict[str, SectionMetadata],
) -> Optional[float]:
    """Estimate section coverage ratio excluding TOC pages."""

    if not pages or not sections:
        return None

    filtered_pages = [page for page in pages if not is_toc_page(page)]
    if not filtered_pages:
        return None

    total_pages = len(filtered_pages)
    covered_indices: set[int] = set()
    for section in sections.values():
        start = getattr(section, "start_page", None)
        end = getattr(section, "end_page", None)
        if start is None:
            continue
        try:
            start_idx = max(0, int(start))
        except (TypeError, ValueError):
            continue
        if end is None:
            end_idx = start_idx
        else:
            try:
                end_idx = int(end)
            except (TypeError, ValueError):
                end_idx = start_idx
        if end_idx < start_idx:
            end_idx = start_idx
        end_idx = min(end_idx, total_pages - 1)
        for idx in range(start_idx, end_idx + 1):
            covered_indices.add(idx)

    if covered_indices:
        page_ratio = len(covered_indices) / total_pages
    else:
        page_ratio = 0.0

    if page_ratio >= 0.1 or page_ratio == 0.0:
        return round(min(1.0, page_ratio), 3)

    # Fallback to character ratio when pagination anchors were unavailable
    total_chars = sum(len(page.text or "") for page in filtered_pages)
    if total_chars <= 0:
        return round(min(1.0, page_ratio), 3)

    section_chars = sum(len(getattr(section, "text", "") or "") for section in sections.values())
    if section_chars <= 0:
        return round(min(1.0, page_ratio), 3)

    char_ratio = min(1.0, section_chars / total_chars)
    return round(char_ratio, 3)


__all__ = ["extract_textbook_chapter"]
