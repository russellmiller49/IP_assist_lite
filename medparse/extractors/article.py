"""Profile-aware article extraction pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from medparse.config import ExtractionConfig, get_extraction_config
from medparse.extract.utils import collect_lines, collect_tables, load_pages, reference_section
from medparse.ingest.models import PageData
from medparse.normalize.article_frontmatter import (
    extract_authors_affiliations,
    extract_coi_and_funding,
    extract_doi,
    extract_bibliographic_metadata,
    extract_title_hierarchical,
)
from medparse.normalize.title_block import extract_title
from medparse.normalize.article_sections import normalize_article_sections
from medparse.normalize.article_yield_ats import DiagnosticYieldATS, extract_ats_compliant_yield
from medparse.normalize.figures_captions import FigureBlock, extract_figures_and_captions
from medparse.normalize.guideline_grades import (
    GuidelineRecommendation as ParsedGuidelineRecommendation,
    parse_guideline_recommendations,
)
from medparse.normalize.outcomes import OutcomeData, extract_outcomes
from medparse.normalize.page_furniture import strip_furniture
from medparse.normalize.relations import RelationRecord, build_cooccurrence, build_relations
from medparse.normalize.tables_classifier import TableBlock, classify_and_gate_tables
from medparse.normalize.umls_linking import (
    UmlsEntity as UmlsEntityRecord,
    UmlsLinkingResult,
    link_umls_entities,
)
from medparse.normalize.references import normalize_references
from medparse.normalize.yields import yield_from_text
from medparse.schema.article import (
    Affiliation,
    ArticleDocument,
    ArticleFigure,
    Author,
    DiagnosticYield,
    EnhancedTable,
    GrantInfo,
    GuidelineRecommendation,
    Outcome,
)
from medparse.schema.common import EvidenceSpan, Relation, UmlsEntity
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)


def extract_article(
    pdf_path: Path,
    *,
    engine: str = "fitz",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
    config: Optional[ExtractionConfig] = None,
) -> ArticleDocument:
    """Extract an article document honouring the configured profile."""

    extraction_config = config or get_extraction_config()
    pages = pages or load_pages(pdf_path, engine=engine, max_pages=page_limit)
    if not pages:
        raise ValueError(f"No pages extracted from {pdf_path}")

    _strip_page_furniture(pages)
    sections = normalize_article_sections(pages)
    flat_lines = collect_lines(pages)

    # Try both title extraction methods and use the better one
    title_info_old = extract_title_hierarchical(pages)
    doi = extract_doi(pages[:2])
    biblio = extract_bibliographic_metadata(pages)

    # Use the new font-aware title extraction
    title, title_source, title_confidence = extract_title(pages, metadata=None, doi=doi)

    # Choose the better title
    if title and title_confidence > title_info_old.get("confidence", 0.0):
        title_info = {
            "title": title,
            "source": title_source,
            "confidence": title_confidence
        }
    else:
        title_info = title_info_old
    frontmatter = extract_authors_affiliations(pages)
    authors = _build_authors(frontmatter)
    affiliations = _build_affiliations(frontmatter.get("affiliations", []))

    table_blocks = _maybe_classify_tables(pages, extraction_config)
    outcomes = _maybe_extract_outcomes(sections, table_blocks, extraction_config)
    diagnostic_yield = _maybe_extract_yield(sections, table_blocks, extraction_config)
    recommendations_raw = _maybe_extract_recommendations(sections, pages, extraction_config)
    recommendations = _map_recommendations(recommendations_raw)
    figures = _maybe_extract_figures(pages, extraction_config)

    doc_subtype = _infer_doc_subtype(title_info, sections, recommendations)

    yield_data = yield_from_text(flat_lines)
    references = normalize_references(
        reference_section(flat_lines),
        mode="article",
        headings=[heading.title for page in pages for heading in page.headings],
    )

    conflicts, funding_statements = _coi_and_funding(pages)
    funding_sources = [
        GrantInfo(agency=statement) for statement in funding_statements if statement != "None"
    ]

    if extraction_config.should_enrich_umls():
        umls_result = link_umls_entities([(page.number, page.text) for page in pages])
    else:
        umls_result = UmlsLinkingResult(status="skipped_disabled", entities=[])
    umls_records = umls_result.entities

    relation_records = (
        build_relations(
            title=title_info.get("title") or pdf_path.stem,
            outcomes=[outcome.model_dump() for outcome in outcomes],
            recommendations=[rec.model_dump() for rec in recommendations],
        )
        if extraction_config.should_extract_relations()
        else []
    )
    if extraction_config.should_extract_relations() and umls_records:
        relation_records.extend(
            build_cooccurrence(
                [record.model_dump() for record in umls_records],
                window="page",
            )
        )

    document = ArticleDocument(
        source_file=str(pdf_path),
        page_count=len(pages),
        title=title_info.get("title"),
        title_confidence=title_info.get("confidence", 0.0),
        title_source=title_info.get("source"),
        doi=doi,
        journal=biblio.get("journal"),
        year=biblio.get("year"),
        volume=biblio.get("volume"),
        issue=biblio.get("issue"),
        sections=sections,
        abstract=sections.get("abstract"),
        authors=authors,
        affiliations=affiliations,
        conflicts_of_interest=conflicts,
        has_no_conflicts=_all_none(conflicts),
        funding_sources=funding_sources,
        has_no_funding=_all_none(funding_statements),
        tables=_map_tables(table_blocks),
        outcomes=_map_outcomes(outcomes),
        diagnostic_yield=_map_yield(diagnostic_yield, yield_data),
        recommendations=recommendations,
        doc_subtype=doc_subtype,
        figures=_map_figures(figures),
        umls_entities=_map_umls_entities(umls_records),
        relations=_map_relations(relation_records),
        n_patients=_as_int(yield_data.get("n_patients")),
        n_lesions=_as_int(yield_data.get("n_lesions")),
        references=references,
    )

    document.pipeline_info["umls_status"] = umls_result.status
    document.pipeline_info["umls"] = umls_result.status
    if umls_result.model_name:
        document.pipeline_info.setdefault("umls_model", umls_result.model_name)
    document.pipeline_info["umls_entities_count"] = len(umls_records)
    document.pipeline_info["doc_subtype"] = doc_subtype

    return document


def _strip_page_furniture(pages: Sequence[PageData]) -> None:
    lines_by_page = [list(page.lines) for page in pages]
    cleaned = strip_furniture(lines_by_page, threshold=0.6)
    for page, clean_lines in zip(pages, cleaned, strict=False):
        page.lines = clean_lines
        page.text = "\n".join(clean_lines)


def _build_authors(frontmatter: dict) -> List[Author]:
    payload = []
    corresponding = frontmatter.get("corresponding_author") or {}
    corresponding_name = (corresponding.get("name") or "").lower()

    corr_email = corresponding.get("email")

    for author in frontmatter.get("authors", []):
        try:
            is_corr = _matches_corresponding(author, corresponding_name)
            payload.append(
                Author(
                    given=author.get("given", ""),
                    family=author.get("family", ""),
                    suffix=author.get("suffix"),
                    affiliation_ids=[
                        marker
                        for marker in author.get("footnotes", [])
                        if marker and marker.isdigit()
                    ],
                    is_corresponding=is_corr,
                    email=corr_email if is_corr else None,
                    footnote_symbols=[
                        marker for marker in author.get("footnotes", []) if not marker.isdigit()
                    ],
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Skipping author due to validation error: %s", exc)
    return payload


def _matches_corresponding(author: dict, corr_lower: str) -> bool:
    if not corr_lower:
        return False
    candidate = f"{author.get('given', '')} {author.get('family', '')}".strip().lower()
    return candidate and candidate in corr_lower


def _build_affiliations(records: Iterable[dict]) -> List[Affiliation]:
    payload: List[Affiliation] = []
    for record in records:
        aff_id = str(record.get("id")) if record.get("id") is not None else None
        text = record.get("text")
        if not text:
            continue
        payload.append(
            Affiliation(
                id=aff_id or str(len(payload) + 1),
                text=text,
            )
        )
    return payload


def _maybe_classify_tables(pages: Sequence[PageData], config: ExtractionConfig) -> List[TableBlock]:
    if not config.is_enriched():
        return []
    raw_tables = collect_tables(pages)
    return classify_and_gate_tables(raw_tables)


def _maybe_extract_outcomes(
    sections: dict[str, str],
    tables: List[TableBlock],
    config: ExtractionConfig,
) -> List[OutcomeData]:
    if not config.is_enriched():
        return []
    return extract_outcomes(sections, tables)


def _maybe_extract_yield(
    sections: dict[str, str],
    tables: List[TableBlock],
    config: ExtractionConfig,
) -> Optional[DiagnosticYieldATS]:
    if not config.is_enriched():
        return None
    return extract_ats_compliant_yield(sections, tables)


def _maybe_extract_recommendations(
    sections: dict[str, str],
    pages: Sequence[PageData],
    config: ExtractionConfig,
) -> List[ParsedGuidelineRecommendation]:
    if not config.should_normalize_guidelines():
        return []
    return parse_guideline_recommendations(sections, list(pages))


def _maybe_extract_figures(
    pages: Sequence[PageData],
    config: ExtractionConfig,
) -> List[FigureBlock]:
    if not config.is_enriched():
        return []
    return extract_figures_and_captions(list(pages))


def _coi_and_funding(pages: Sequence[PageData]) -> tuple[List[str], List[str]]:
    data = extract_coi_and_funding(list(pages))
    return data.get("conflicts", []), data.get("funding", [])


def _map_tables(blocks: Sequence[TableBlock]) -> List[EnhancedTable]:
    tables: List[EnhancedTable] = []
    for idx, block in enumerate(blocks, start=1):
        tables.append(
            EnhancedTable(
                id=f"table_{idx}",
                caption=block.caption,
                headers=[block.headers],
                rows=block.rows,
                page=block.page,
                table_type=block.table_type,
            )
        )
    return tables


def _map_outcomes(outcomes: Sequence[OutcomeData]) -> List[Outcome]:
    mapped: List[Outcome] = []
    for outcome in outcomes:
        evidence = (
            EvidenceSpan(text=outcome.evidence_text, page=outcome.page, confidence=0.8)
            if outcome.evidence_text
            else None
        )
        mapped.append(
            Outcome(
                name=outcome.name,
                n=outcome.n,
                percent=outcome.percent,
                value=outcome.value,
                denominator=outcome.denominator,
                ci_lower=outcome.ci_lower,
                ci_upper=outcome.ci_upper,
                linked_figure_table=outcome.linked_figure_table,
                evidence=evidence,
            )
        )
    return mapped


def _map_yield(
    data: Optional[DiagnosticYieldATS],
    fallback: Optional[dict],
) -> Optional[DiagnosticYield]:
    if not data:
        if not fallback:
            return None
        fraction = fallback.get("diagnostic_yield_fraction")
        pct = fallback.get("diagnostic_yield_pct")
        numerator = denominator = None
        if fraction and isinstance(fraction, tuple) and len(fraction) == 2:
            numerator, denominator = fraction
        if numerator is not None and denominator:
            value = (numerator / denominator) * 100
        else:
            value = pct
        if value is None:
            return None
        exclusion_reasons: List[str] = []
        if numerator is None:
            exclusion_reasons.append("no_numerator_in_text")
        if denominator is None:
            exclusion_reasons.append("no_denominator_in_text")

        return DiagnosticYield(
            value=value,
            reported_value=(value / 100.0) if value is not None else None,
            numerator=int(numerator) if numerator is not None else None,
            denominator=int(denominator) if denominator is not None else None,
            strict=False,
            exclusion_reasons=exclusion_reasons,
        )
    evidence = (
        EvidenceSpan(text=data.evidence.text, confidence=data.evidence.confidence)
        if data.evidence
        else None
    )
    return DiagnosticYield(
        value=data.yield_pct,
        reported_value=(data.yield_pct / 100.0) if data.yield_pct is not None else None,
        numerator=data.numerator,
        denominator=data.denominator,
        lower_ci=data.ci_lower,
        upper_ci=data.ci_upper,
        exclusion_reasons=data.exclusion_reasons,
        method_note=data.definition,
        compatible_with_ats=data.compatible_with_ats,
        strict=data.strict,
        evidence=evidence,
    )


def _map_recommendations(
    items: Sequence[ParsedGuidelineRecommendation],
) -> List[GuidelineRecommendation]:
    mapped: List[GuidelineRecommendation] = []
    for item in items:
        evidence = EvidenceSpan(text=item.text[:200], page=item.page, confidence=0.7)
        mapped.append(
            GuidelineRecommendation(
                label=getattr(item, "number", None),
                text=item.text,
                grade=getattr(item, "grade", None),
                strength=getattr(item, "strength", None),
                strength_scale=getattr(item, "strength_scale", None),
                evidence_level=getattr(item, "evidence_level", None),
                votes=getattr(item, "votes", None),
                consensus_percentage=getattr(item, "consensus_percentage", None),
                statement_type=getattr(item, "statement_type", "graded" if getattr(item, "grade", None) else "ungraded"),
                evidence=evidence,
                page_span=(item.page, item.page) if item.page is not None else None,
            )
        )
    return mapped


def _map_figures(figures: Sequence[FigureBlock]) -> List[ArticleFigure]:
    mapped: List[ArticleFigure] = []
    for figure in figures:
        mapped.append(
            ArticleFigure(
                label=figure.label,
                caption=figure.caption,
                page=figure.page,
            )
        )
    return mapped


def _infer_doc_subtype(
    title_info: dict,
    sections: dict[str, str],
    recommendations: Sequence[GuidelineRecommendation],
) -> str:
    """Rule-based subtype detection for articles.

    Priority order:
    1. Explicit guideline markers in title/text
    2. Presence of graded recommendations
    3. Review markers
    4. Default to research
    """

    # Get title for checking
    title = (title_info.get("title") or "").lower() if isinstance(title_info, dict) else ""

    # Priority 1: Explicit guideline markers in title or first pages
    guideline_markers = [
        "guideline",
        "statement",
        "recommendations",
        "consensus",
        "task force",
        "position paper",
        "best practice",
        "grade",
        "sign",
        "accp",
        "chest guideline",
        "ats/ers",
        "official ats",
    ]

    # Check title first
    for marker in guideline_markers:
        if marker in title:
            LOGGER.debug(f"Detected guideline from title marker: {marker}")
            return "guideline"

    # Check abstract/intro for guideline language
    intro_text = (sections.get("introduction", "") + " " + sections.get("abstract", ""))[:2000].lower()
    guideline_phrases = [
        "clinical practice guideline",
        "evidence-based recommendations",
        "guideline recommendations",
        "grading of recommendations",
        "systematic review of evidence for recommendations",
        "this guideline",
        "these recommendations",
    ]

    for phrase in guideline_phrases:
        if phrase in intro_text:
            LOGGER.debug(f"Detected guideline from intro/abstract phrase: {phrase}")
            return "guideline"

    # Priority 2: Has graded recommendations
    has_graded = any(rec.grade for rec in recommendations)
    has_guideline_marker = any(
        rec.statement_type in {"good_practice", "consensus", "ungraded"}
        for rec in recommendations
    )
    if has_graded or has_guideline_marker:
        LOGGER.debug(f"Detected guideline from recommendations: graded={has_graded}, markers={has_guideline_marker}")
        return "guideline"

    # Priority 3: Check if it has many recommendation-like statements
    if len(recommendations) >= 5:
        LOGGER.debug(f"Detected guideline from high recommendation count: {len(recommendations)}")
        return "guideline"

    # Priority 4: Review markers
    review_markers = [
        "systematic review",
        "literature review",
        "meta-analysis",
        "scoping review",
        "narrative review",
    ]
    if any(marker in title for marker in review_markers):
        LOGGER.debug(f"Detected review from title")
        return "review"

    # Check section headings for review
    for heading in sections.keys():
        if heading and any(marker in heading.lower() for marker in ["review", "meta-analysis"]):
            LOGGER.debug(f"Detected review from section heading: {heading}")
            return "review"

    # Default to research
    LOGGER.debug("Defaulting to research article subtype")
    return "research"


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
        evidence = (
            EvidenceSpan(text=record.evidence, confidence=0.7)
            if record.evidence
            else None
        )
        mapped.append(
            Relation(
                subject=record.subject,
                predicate=record.predicate,
                object=record.object,
                attributes=record.attributes,
                evidence=evidence,
            )
        )
    return mapped


def _all_none(statements: Sequence[str]) -> bool:
    if not statements:
        return False
    normalized = [s.strip().lower() for s in statements]
    return all(s in {"none", "none declared"} for s in normalized)


def _as_int(value: Optional[float]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["extract_article"]
