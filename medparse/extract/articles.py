"""Research article extraction pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Sequence

from medparse.extract.utils import (
    collect_lines,
    collect_tables,
    iter_section_windows,
    load_pages,
    reference_section,
    section_text_between,
)
from medparse.ingest.models import PageData
from medparse.normalize.metadata import normalize_article_metadata
from medparse.normalize.references import normalize_references
from medparse.normalize.yields import yield_from_text
from medparse.schema.article import ArticleDocument, Outcome, YieldSummary
from medparse.schema.common import EvidenceSpan


COMPLICATION_KEYWORDS = {
    "pneumothorax": re.compile(r"pneumothora(?:x|ces)\b", re.IGNORECASE),
    "bleeding": re.compile(r"(major|significant)?\s*bleeding", re.IGNORECASE),
    "hemorrhage": re.compile(r"hemorrhag", re.IGNORECASE),
}
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def extract_article(
    pdf_path: Path,
    *,
    engine: str = "pymupdf",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
) -> ArticleDocument:
    """Extract structured data for a research article."""

    pages = pages or load_pages(pdf_path, engine=engine, max_pages=page_limit)
    lines = collect_lines(pages)
    page_count = len(pages)

    sections = {}
    evidences = {}
    for heading, next_heading in iter_section_windows(pages):
        text, evidence, _lines = section_text_between(pages, heading, next_heading)
        sections[heading.title.lower()] = text
        evidences[heading.title.lower()] = evidence

    title = _derive_title(pages)
    abstract = sections.get("abstract")
    imprint_lines = pages[0].lines[:20] if pages else []
    article_meta = normalize_article_metadata(title, imprint_lines)

    yield_data = yield_from_text(lines)
    yield_summary = _build_yield_summary(yield_data)

    outcomes = _extract_complications(lines)
    tables = collect_tables(pages)
    headings = [heading.title for page in pages for heading in page.headings]
    references = normalize_references(
        reference_section(lines),
        mode="article",
        headings=headings,
    )

    document = ArticleDocument(
        doc_type="article",
        source_file=str(pdf_path),
        page_count=page_count,
        title=article_meta.get("title"),
        abstract=abstract,
        year=article_meta.get("year"),
        n_patients=_as_int(yield_data.get("n_patients")),
        n_lesions=_as_int(yield_data.get("n_lesions")),
        outcomes=outcomes,
        yield_summary=yield_summary,
        tables=tables,
        references=references,
    )
    return document


def _derive_title(pages: Sequence) -> str | None:
    for page in pages:
        for heading in page.headings:
            if heading.level == 1 and heading.kind == "section":
                return heading.title
    if pages and pages[0].lines:
        return pages[0].lines[0]
    return None


def _build_yield_summary(yield_data: dict) -> YieldSummary | None:
    fraction = yield_data.get("diagnostic_yield_fraction")
    if fraction:
        numerator, denominator = fraction
        strict_yield = (numerator / denominator) if denominator else None
        return YieldSummary(
            strict_numerator=int(numerator),
            strict_denominator=int(denominator),
            strict_yield=strict_yield,
            notes=None,
            evidence=None,
        )

    pct = yield_data.get("diagnostic_yield_pct")
    if pct is not None:
        return YieldSummary(
            strict_numerator=None,
            strict_denominator=None,
            strict_yield=float(pct) / 100.0,
            notes="Reported study-level diagnostic yield",
            evidence=None,
        )
    return None


def _extract_complications(lines: Sequence[str]) -> List[Outcome]:
    text_blob = " ".join(lines)
    outcomes: List[Outcome] = []
    for name, pattern in COMPLICATION_KEYWORDS.items():
        match = pattern.search(text_blob)
        if not match:
            continue
        vicinity = text_blob[max(match.start() - 60, 0) : match.end() + 60]
        value = _extract_percent(vicinity)
        unit = "percent" if value is not None else None
        outcomes.append(
            Outcome(
                name=name,
                value=value,
                unit=unit,
                evidence=EvidenceSpan(text=vicinity[:160], confidence=0.8),
            )
        )
    return outcomes


def _extract_percent(text: str) -> float | None:
    match = PERCENT_RE.search(text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _as_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


__all__ = ["extract_article"]
