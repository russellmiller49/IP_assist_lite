"""Profile-aware article extraction pipeline."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from medparse.config import ExtractionConfig, get_extraction_config
from medparse.extract.utils import collect_lines, collect_tables, load_pages, reference_section
from medparse.ingest.models import PageData
from medparse.normalize.article_frontmatter import (
    extract_authors_affiliations,
    extract_coi_and_funding,
    extract_doi,
    extract_bibliographic_metadata,
    extract_title_hierarchical,
    is_valid_title,
    link_authors_to_affiliations,
)
from medparse.normalize.title_block import extract_title
from medparse.normalize.article_sections import normalize_article_sections
from medparse.normalize.article_yield_ats import (
    ATS_REASON_DERIVED,
    ATS_REASON_FOLLOW_UP,
    ATS_REASON_NO_N_OVER_N,
    ATS_REASON_NONSPECIFIC,
    DiagnosticYieldATS,
    extract_ats_compliant_yield,
)
from medparse.normalize.figures_captions import FigureBlock, extract_figures_and_captions
from medparse.normalize.guideline_grades import (
    GuidelineRecommendation as ParsedGuidelineRecommendation,
    parse_guideline_recommendations,
)
from medparse.normalize.outcomes import OutcomeData, extract_outcomes
from medparse.normalize.page_furniture import strip_furniture
from medparse.normalize.relations import RelationRecord, build_cooccurrence, build_relations
from medparse.normalize.zotero_map import (
    FrontMatter,
    configure_zotero_library,
    lookup_front_matter,
)
from medparse.normalize.tables_classifier import TableBlock, classify_and_gate_tables
from medparse.normalize.umls_linking import (
    UmlsEntity as UmlsEntityRecord,
    UmlsLinkingResult,
    link_entities,
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
from medparse.text.paragraphizer import build_paragraph_store
from medparse.utils.log import get_logger
from medparse.guideline.promoter import enrich_guideline_document

LOGGER = get_logger(__name__)
UMLS_PAGE_CACHE: Dict[str, List[UmlsEntityRecord]] = {}
ATS_CANONICAL_REASONS = {
    ATS_REASON_NO_N_OVER_N,
    ATS_REASON_FOLLOW_UP,
    ATS_REASON_NONSPECIFIC,
    ATS_REASON_DERIVED,
}


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
    pages_for_detection = [copy.deepcopy(page) for page in pages]
    sections_for_detection = normalize_article_sections(pages_for_detection)
    if not pages:
        raise ValueError(f"No pages extracted from {pdf_path}")

    _strip_page_furniture(pages)
    sections = normalize_article_sections(pages)
    flat_lines = collect_lines(pages)

    # Try both title extraction methods and use the better one
    doi = extract_doi(pages[:2])
    biblio = extract_bibliographic_metadata(pages)
    fallback_title = pdf_path.stem.replace("_", " ").strip()
    title_info = extract_title_hierarchical(
        pages,
        metadata=None,
        doi=doi,
        fallback=fallback_title,
    )

    # Use the font-aware extractor as a candidate but guard against headers
    title_candidate, title_source, title_confidence = extract_title(pages, metadata=None, doi=doi)
    best_confidence = float(title_info.get("confidence", 0.0) or 0.0)
    if (
        title_candidate
        and is_valid_title(title_candidate)
        and title_confidence >= best_confidence
    ):
        title_info = {
            "title": title_candidate,
            "source": title_source,
            "confidence": title_confidence,
        }
    elif not title_info.get("title") and fallback_title:
        title_info = {
            "title": fallback_title,
            "source": title_info.get("source") or "filename",
            "confidence": max(best_confidence, 0.25),
        }
    frontmatter = extract_authors_affiliations(pages)
    authors = _build_authors(frontmatter)
    affiliations = _build_affiliations(frontmatter.get("affiliations", []))
    zotero_match: Optional[FrontMatter] = None
    fm_info: Optional[Dict[str, object]] = None
    zotero_author_count = 0
    journal_value = biblio.get("journal")
    year_value = biblio.get("year")

    if extraction_config.should_use_zotero():
        zotero_path = extraction_config.metadata_sources.get("zotero_json")
        configure_zotero_library(zotero_path)
        if zotero_path:
            try:
                zotero_match = lookup_front_matter(doi, title_info.get("title"))
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.debug("Zotero lookup failed for %s: %s", pdf_path.name, exc)
                fm_info = {
                    "status": "error",
                    "detail": str(exc),
                    "source": "zotero",
                }
        else:
            fm_info = {"status": "library_unavailable", "source": "zotero"}

    if zotero_match:
        zotero_author_count = len(zotero_match.authors)
        fm_info = {
            "status": "linked",
            "source": "zotero",
            "method": zotero_match.match_method,
            "score": zotero_match.match_score,
            "id": zotero_match.entry_id,
        }
        if zotero_match.title:
            current_confidence = float(title_info.get("confidence", 0.0) or 0.0)
            if not title_info.get("title") or zotero_match.match_score >= current_confidence:
                title_info["title"] = zotero_match.title
                title_info["source"] = "zotero"
            title_info["confidence"] = max(current_confidence, zotero_match.match_score)
        if zotero_match.doi and not doi:
            doi = zotero_match.doi
        if zotero_match.authors:
            authors = _authors_from_front_matter(zotero_match)
        if zotero_match.affiliations:
            affiliations = _affiliations_from_front_matter(zotero_match)
        if zotero_match.journal:
            journal_value = zotero_match.journal
        if zotero_match.year is not None:
            year_value = zotero_match.year
    elif fm_info is None and extraction_config.should_use_zotero():
        fm_info = {"status": "not_found", "source": "zotero"}

    link_authors_to_affiliations(authors, affiliations, list(pages))

    table_blocks = _maybe_classify_tables(pages, extraction_config)
    outcomes = _maybe_extract_outcomes(sections, table_blocks, extraction_config)
    diagnostic_yield = _maybe_extract_yield(sections, table_blocks, extraction_config)
    recommendations_raw = _maybe_extract_recommendations(sections, pages, extraction_config)
    recommendations = _map_recommendations(recommendations_raw)
    figures = _maybe_extract_figures(pages, extraction_config)
    yield_definitions_present = _detect_yield_definition_signals(
        pages_for_detection,
        sections,
        table_blocks,
    )

    doc_subtype = _infer_doc_subtype(
        pages_for_detection,
        title_info,
        sections_for_detection,
        recommendations,
        recommendations_raw,
    )
    if doc_subtype not in {"guideline", "statement", "classification"} and "guideline" in pdf_path.stem.lower():
        if recommendations:
            doc_subtype = "guideline"

    yield_data = yield_from_text(flat_lines)
    if diagnostic_yield:
        lesion_hint = getattr(diagnostic_yield, "lesion_denominator", None)
        if lesion_hint:
            existing_lesions = _as_int(yield_data.get("n_lesions"))
            if not existing_lesions or existing_lesions != lesion_hint:
                yield_data["n_lesions"] = lesion_hint
        patient_hint = getattr(diagnostic_yield, "patient_denominator", None)
        if patient_hint:
            existing_patients = _as_int(yield_data.get("n_patients"))
            if not existing_patients:
                yield_data["n_patients"] = patient_hint
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
        try:
            umls_result = link_entities(
                list(pages),
                cache=UMLS_PAGE_CACHE,
                enabled=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("UMLS linking failed: %s", exc)
            umls_result = UmlsLinkingResult(status="skipped_model_missing", entities=[])
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
                window=extraction_config.relation_window or "page",
            )
        )

    document = ArticleDocument(
        source_file=str(pdf_path),
        page_count=len(pages),
        title=title_info.get("title"),
        title_confidence=title_info.get("confidence", 0.0),
        title_source=title_info.get("source"),
        doi=doi,
        journal=journal_value,
        year=year_value,
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
        yield_definitions_present=yield_definitions_present,
        recommendations=recommendations,
        doc_subtype=doc_subtype,
        figures=_map_figures(figures),
        umls_entities=_map_umls_entities(umls_records),
        relations=_map_relations(relation_records),
        n_patients=_as_int(yield_data.get("n_patients")),
        n_lesions=_as_int(yield_data.get("n_lesions")),
        references=references,
    )

    if zotero_match:
        document.front_matter_source = "zotero"
        document.front_matter_confidence = zotero_match.match_score
        if zotero_author_count > 0 and not document.authors:
            warning_list = document.pipeline_info.setdefault("front_matter_warnings", [])
            if isinstance(warning_list, list):
                warning_list.append("authors_missing_despite_zotero_match")


    document.pipeline_info["umls_status"] = umls_result.status
    document.pipeline_info["umls"] = umls_result.status
    if umls_result.umls_model:
        document.pipeline_info.setdefault("umls_model", umls_result.umls_model)
    document.pipeline_info["umls_entities_count"] = len(umls_records)
    document.pipeline_info["doc_subtype"] = doc_subtype
    if yield_definitions_present is not None:
        document.pipeline_info["yield_definitions_present"] = bool(yield_definitions_present)
    if fm_info:
        document.pipeline_info["front_matter"] = fm_info
    if extraction_config.relation_window:
        document.pipeline_info["relation_window"] = extraction_config.relation_window
    if extraction_config.max_entities:
        document.pipeline_info["max_entities"] = extraction_config.max_entities
    if extraction_config.max_relations:
        document.pipeline_info["max_relations"] = extraction_config.max_relations

    paragraph_store, dedup_applied = build_paragraph_store(
        document.doc_id,
        pages,
        join_hyphens=True,
        drop_headers=True,
        drop_footers=True,
    )
    document.paragraph_store = paragraph_store
    if dedup_applied:
        document.pipeline_info["paragraph_dedup_applied"] = True
    else:
        document.pipeline_info.setdefault("paragraph_dedup_applied", False)

    enrich_guideline_document(document, pages)

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


def _authors_from_front_matter(front_matter: FrontMatter) -> List[Author]:
    authors: List[Author] = []
    for author in front_matter.authors:
        try:
            authors.append(
                Author(
                    given=author.given or "",
                    family=author.family or "",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Skipping Zotero author due to validation error: %s", exc)
    return authors


def _affiliations_from_front_matter(front_matter: FrontMatter) -> List[Affiliation]:
    affiliations: List[Affiliation] = []
    for idx, text in enumerate(front_matter.affiliations, start=1):
        if not text:
            continue
        try:
            affiliations.append(
                Affiliation(
                    id=str(idx),
                    text=text,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Skipping Zotero affiliation due to validation error: %s", exc)
    return affiliations


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
        if numerator is None or denominator is None:
            exclusion_reasons.append(ATS_REASON_NO_N_OVER_N)
            if value is not None:
                exclusion_reasons.append(ATS_REASON_DERIVED)
        exclusion_reasons = [
            reason for reason in dict.fromkeys(exclusion_reasons) if reason in ATS_CANONICAL_REASONS
        ]

        return DiagnosticYield(
            value=value,
            reported_value=(value / 100.0) if value is not None else None,
            numerator=int(numerator) if numerator is not None else None,
            denominator=int(denominator) if denominator is not None else None,
            strict=False,
            exclusion_reasons=exclusion_reasons,
            compatible_with_ats=False,
        )
    reasons = list(dict.fromkeys(data.exclusion_reasons))
    numerator_val = data.numerator
    denominator_val = data.denominator
    if numerator_val is None or denominator_val is None:
        if ATS_REASON_NO_N_OVER_N not in reasons:
            reasons.append(ATS_REASON_NO_N_OVER_N)
        if data.yield_pct is not None and ATS_REASON_DERIVED not in reasons:
            reasons.append(ATS_REASON_DERIVED)
    reasons = [reason for reason in dict.fromkeys(reasons) if reason in ATS_CANONICAL_REASONS]
    derived = ATS_REASON_DERIVED in reasons
    evidence = None
    if data.evidence:
        evidence = EvidenceSpan(
            text=data.evidence.text,
            page=data.evidence.page,
            confidence=data.evidence.confidence,
        )
    compatible = (
        data.compatible_with_ats
        and not derived
        and numerator_val is not None
        and denominator_val is not None
    )
    strict_flag = (
        data.strict
        and not derived
        and numerator_val is not None
        and denominator_val is not None
    )
    if ATS_REASON_NO_N_OVER_N in reasons and (numerator_val is None or denominator_val is None):
        numerator_val = None
        denominator_val = None
        compatible = False
        strict_flag = False
    return DiagnosticYield(
        value=data.yield_pct,
        reported_value=(data.yield_pct / 100.0) if data.yield_pct is not None else None,
        numerator=numerator_val,
        denominator=denominator_val,
        lower_ci=data.ci_lower,
        upper_ci=data.ci_upper,
        exclusion_reasons=reasons,
        method_note=data.definition,
        compatible_with_ats=compatible,
        strict=strict_flag,
        evidence=evidence,
        denominator_hint=getattr(data, "denominator_hint", None),
    )


def _map_recommendations(
    items: Sequence[ParsedGuidelineRecommendation],
) -> List[GuidelineRecommendation]:
    mapped: List[GuidelineRecommendation] = []
    for item in items:
        evidence = EvidenceSpan(text=item.text[:200], page=item.page, confidence=0.7)
        statement_type = getattr(item, "statement_type", None)
        if statement_type == "good_practice":
            statement_type = "ungraded"
        grade_value = getattr(item, "grade", None)
        mapped.append(
            GuidelineRecommendation(
                label=getattr(item, "number", None),
                text=item.text,
                grade=grade_value,
                grade_raw=grade_value,
                strength=getattr(item, "strength", None),
                strength_scale=getattr(item, "strength_scale", None),
                evidence_level=getattr(item, "evidence_level", None),
                votes=getattr(item, "votes", None),
                consensus_percentage=getattr(item, "consensus_percentage", None),
                statement_type=statement_type or ("graded" if getattr(item, "grade", None) else "ungraded"),
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


GUIDELINE_KEYWORDS = {
    "recommendation grade",
    "recommendation level",
    "grading of recommendations",
    "good practice statement",
    "consensus recommendation",
    "grade of recommendation",
    "grade evidence",
    "accp",
    "sign",
    "evidence level",
}

GRADE_BANNER_TOKENS = ("grade", "accp")
GRADE_SIGN_PATTERN = re.compile(r"\bSIGN\b")

GUIDELINE_FIRST_PAGE_MARKERS = {
    "guideline",
    "clinical practice guideline",
    "practice guideline",
    "consensus statement",
    "american thoracic society documents",
    "american college of chest physicians",
    "chest guideline",
    "esge",
    "ers",
    "ests",
    "accp",
    "ats guideline",
}

RECOMMENDATION_ANCHORS_PATTERN = re.compile(r"\bwe\s+(?:recommend|suggest)\b", re.IGNORECASE)
GUIDELINE_GRADE_PATTERN = re.compile(r"recommendation\s+grade\s+[A-D]", re.IGNORECASE)
STATEMENT_TITLE_MARKERS = (
    "statement",
    "research statement",
    "framework",
    "update",
    "official statement",
)
STATEMENT_HEADER_MARKERS = (
    "american thoracic society documents",
    "official american thoracic society documents",
    "an official american thoracic society",
)
CLASSIFICATION_TITLE_MARKERS = (
    "classification",
    "classifications",
    "classification update",
)
CLASSIFICATION_SUPPORT_MARKERS = (
    "update",
    "revision",
    "framework",
)


def _count_grade_banner_hits(text: Optional[str]) -> int:
    if not text:
        return 0
    hits = 0
    lowered = text.lower()
    for token in GRADE_BANNER_TOKENS:
        hits += len(re.findall(rf"\b{token}\b", lowered))
    hits += len(GRADE_SIGN_PATTERN.findall(text))
    return hits


def _has_summary_statements(pages: Sequence[PageData]) -> bool:
    for page in pages:
        content_parts = []
        if page.lines:
            content_parts.extend(line.strip() for line in page.lines if line.strip())
        if page.text:
            content_parts.append(page.text)
        combined = " ".join(content_parts).lower()
        if "summary statement" in combined:
            return True
    return False


def _first_page_text(pages: Sequence[PageData], *, max_lines: int = 40) -> str:
    if not pages:
        return ""
    first_page = pages[0]
    lines = (first_page.lines or [])[:max_lines]
    text = " ".join(line.strip() for line in lines if line.strip())
    if text:
        return text
    return (first_page.text or "").strip()


def _count_recommendation_phrases(pages: Sequence[PageData]) -> int:
    hits = 0
    for page in pages:
        content = page.text or " ".join(page.lines or [])
        if not content:
            continue
        hits += len(RECOMMENDATION_ANCHORS_PATTERN.findall(content))
        if hits >= 5:
            break
    return hits


def _has_recommendations_heading(
    pages: Sequence[PageData],
    sections: dict[str, str],
) -> bool:
    if any(
        heading and "recommendation" in heading.lower()
        for heading in sections.keys()
    ):
        return True
    for page in pages[:6]:
        for heading in getattr(page, "headings", []):
            title = (heading.title or "").strip().lower()
            if not title:
                continue
            if "recommendation" in title:
                return True
    return False


def _guideline_signal_score(
    pages: Sequence[PageData],
    sections: dict[str, str],
    recommendations: Sequence[GuidelineRecommendation],
) -> int:
    score = 0
    if recommendations and len(recommendations) >= 5:
        score += 1
    if _count_recommendation_phrases(pages) >= 5:
        score += 1
    banner_text = " ".join(
        (page.text or " ".join(page.lines or [])) for page in pages[:3]
    )
    if GUIDELINE_GRADE_PATTERN.search(banner_text):
        score += 1
    if _has_recommendations_heading(pages, sections):
        score += 1
    return score


def _has_recommendation_grade_signal(
    pages: Sequence[PageData],
    sections: dict[str, str],
) -> bool:
    section_texts = (sections or {}).values()
    if any("recommendation grade" in (text or "").lower() for text in section_texts):
        return True
    for page in pages[:6]:
        content = page.text or " ".join(page.lines or [])
        if "recommendation grade" in (content or "").lower():
            return True
    return False


def looks_like_guideline(
    pages: Sequence[PageData],
    sections: dict[str, str],
    recommendations: Sequence[GuidelineRecommendation],
    raw_recommendations: Sequence[ParsedGuidelineRecommendation] | None = None,
) -> bool:
    try:
        if detect_guideline(pages, sections, recommendations, raw_recommendations):
            return True
    except Exception:  # pragma: no cover - defensive
        pass
    score = _guideline_signal_score(pages, sections, recommendations)
    if (raw_recommendations or recommendations) and score >= 1:
        score += 1
    return score >= 2


def _classification_signal_score(
    pages: Sequence[PageData],
    title_value: str,
) -> int:
    score = 0
    title_lower = title_value.lower()
    if any(marker in title_lower for marker in CLASSIFICATION_TITLE_MARKERS):
        score += 1
    if any(marker in title_lower for marker in CLASSIFICATION_SUPPORT_MARKERS):
        score += 1
    if "idiopathic interstitial pneumonia" in title_lower or "iip" in title_lower:
        score += 1

    first_text = _first_page_text(pages)
    lowered_first = first_text.lower()
    if "classification" in lowered_first and any(
        marker in lowered_first for marker in CLASSIFICATION_SUPPORT_MARKERS
    ):
        score += 1
    for page in pages[:4]:
        for heading in getattr(page, "headings", []):
            heading_text = (heading.title or "").lower()
            if "classification" in heading_text:
                score += 1
                break
    return score


def looks_like_classification_update(
    pages: Sequence[PageData],
    title_value: str,
) -> bool:
    if not title_value:
        return False
    score = _classification_signal_score(pages, title_value)
    return score >= 2


def looks_like_statement(
    pages: Sequence[PageData],
    title_value: str,
    sections: dict[str, str],
) -> bool:
    if not pages:
        return False
    first_text = _first_page_text(pages)
    lowered_first = first_text.lower()
    title_lower = title_value.lower()

    classification_score = _classification_signal_score(pages, title_value)
    if classification_score >= 2:
        return False

    score = 0
    if any(marker in lowered_first for marker in STATEMENT_HEADER_MARKERS):
        score += 2
    if any(marker in title_lower for marker in STATEMENT_TITLE_MARKERS):
        score += 1
    if "american thoracic society" in title_lower and "statement" in title_lower:
        score += 1
    if "an official american thoracic society" in lowered_first:
        score += 1

    intro_text = sections.get("introduction") or ""
    background_text = sections.get("background") or ""
    combined = f"{intro_text} {background_text}".lower()
    if "american thoracic society" in combined and "statement" in combined:
        score += 1

    return score >= 2


def _detect_yield_definition_signals(
    pages: Sequence[PageData],
    sections: dict[str, str],
    tables: Sequence[TableBlock] | None,
) -> bool:
    texts: List[str] = []
    for key in ("methods", "results", "introduction", "abstract"):
        value = sections.get(key)
        if isinstance(value, str) and value:
            texts.append(value.lower())

    early_pages_text = " ".join(
        (page.text or " ".join(page.lines or [])) for page in pages[:4]
    ).lower()
    if early_pages_text:
        texts.append(early_pages_text)

    combined_text = " ".join(texts)
    if any(marker in combined_text for marker in YIELD_DEFINITION_MARKERS):
        return True

    if tables:
        for table in tables:
            caption = (getattr(table, "caption", "") or "").lower()
            label = (getattr(table, "table_type", "") or "").lower()
            headers = " ".join(getattr(table, "headers", []) or []).lower()
            first_rows = " ".join(" ".join(row) for row in (table.rows or [])[:3]).lower()
            table_text = " ".join((caption, label, headers, first_rows))
            if any(token in table_text for token in YIELD_DEFINITION_TABLE_MARKERS):
                return True
    return False

GUIDELINE_TITLE_MARKERS = {
    "guideline",
    "consensus statement",
    "clinical practice guideline",
    "best practice",
    "task force statement",
    "policy statement",
    "position statement",
    "position paper",
    "recommendations",
}

GUIDELINE_HEADING_TOKENS = {
    "recommendation",
    "recommendations",
    "graded recommendation",
    "clinical recommendations",
    "guideline recommendations",
}

GRADE_FRIENDLY_TYPES = {"ungraded", "consensus", "good_practice"}

REVIEW_MARKERS = {
    "systematic review",
    "meta-analysis",
    "scoping review",
    "narrative review",
    "literature review",
}

YIELD_DEFINITION_MARKERS = (
    "strict definition of diagnostic yield",
    "diagnostic yield was defined",
    "diagnostic yield defined as",
    "diagnostic outcome measures",
    "diagnostic outcomes were defined",
    "stard flow",
    "stard diagram",
    "stard flowchart",
    "stard reporting",
)
YIELD_DEFINITION_TABLE_MARKERS = (
    "diagnostic outcome measures",
    "definition of diagnostic yield",
    "diagnostic definitions",
    "diagnostic categories",
)


def detect_guideline(
    pages: Sequence[PageData],
    sections: dict[str, str],
    recommendations: Sequence[GuidelineRecommendation],
    raw_recommendations: Sequence[ParsedGuidelineRecommendation] | None = None,
) -> bool:
    """Return ``True`` when guideline signals are detected across pages."""

    graded_pages: set[int] = set()
    if recommendations:
        for rec in recommendations:
            if rec.page is None:
                continue
            if rec.grade or rec.statement_type in GRADE_FRIENDLY_TYPES:
                graded_pages.add(rec.page)

    if raw_recommendations:
        for rec in raw_recommendations:
            if rec.page is None:
                continue
            if getattr(rec, "grade", None) or getattr(rec, "statement_type", "") in GRADE_FRIENDLY_TYPES:
                graded_pages.add(rec.page)

    if graded_pages:
        LOGGER.debug("Guideline detected via graded recommendation pages: %s", sorted(graded_pages))
        return True

    if recommendations and len(recommendations) >= 5:
        graded_count = sum(
            1
            for rec in recommendations
            if rec.grade or rec.statement_type in GRADE_FRIENDLY_TYPES
        )
        grade_ratio = graded_count / len(recommendations)
        if grade_ratio >= 0.5:
            LOGGER.debug("Guideline detected via recommendation grades ratio=%.2f", grade_ratio)
            return True

    early_text = " ".join(
        page.text or ""
        for page in pages[:4]
        if page.text
    ).lower()
    keyword_hits = sum(1 for keyword in GUIDELINE_KEYWORDS if keyword in early_text)
    if keyword_hits >= 2 and recommendations:
        LOGGER.debug("Guideline detected via keyword match (%d hits).", keyword_hits)
        return True

    intro_and_abstract = " ".join(
        sections.get(key, "") or ""
        for key in ("abstract", "background", "introduction")
    ).lower()
    if recommendations and any(marker in intro_and_abstract for marker in GUIDELINE_TITLE_MARKERS):
        LOGGER.debug("Guideline detected via section markers.")
        return True

    heading_hits = _recommendation_heading_hits(pages)
    if heading_hits >= 1 and recommendations:
        LOGGER.debug("Guideline detected via page headings (hits=%d).", heading_hits)
        return True

    recommendation_pages = 0
    bullet_pattern = re.compile(
        r"^(?:\d{1,2}[\.\)]|[A-Z][\.\)]|[\u2022\-*])\s*(?:recommend|guideline|consensus|good practice|grade)",
        flags=re.IGNORECASE,
    )
    for page in pages:
        if not page.lines:
            continue
        hits = sum(1 for line in page.lines if bullet_pattern.match(line.strip()))
        if hits >= 3:
            recommendation_pages += 1
        if recommendation_pages >= 2:
            LOGGER.debug("Guideline detected via multi-page recommendation blocks.")
            return True

    return False


def _infer_doc_subtype(
    pages: Sequence[PageData],
    title_info: dict,
    sections: dict[str, str],
    recommendations: Sequence[GuidelineRecommendation],
    raw_recommendations: Sequence[ParsedGuidelineRecommendation] | None = None,
) -> str:
    """Classify article subtype using guideline and review detectors."""

    if isinstance(title_info, dict):
        title_value = str(title_info.get("title") or "")
    else:
        title_value = str(title_info or "")
    title_lower = title_value.lower()

    if "guideline" in title_lower and "statement" in title_lower and recommendations:
        return "guideline"

    if "official american thoracic society" in title_lower or "official ats" in title_lower:
        return "statement"

    if "official statement" in title_lower or "consensus statement" in title_lower:
        return "statement"

    if "consensus" in title_lower and "statement" not in title_lower and (
        "official" in title_lower or "american thoracic society" in title_lower
    ):
        return "statement"

    if (
        "statement" in title_lower
        and "guideline" not in title_lower
        and ("official" in title_lower or "consensus" in title_lower or "classification" in title_lower)
    ):
        return "statement"

    if "update" in title_lower and ("official" in title_lower or "statement" in title_lower or "consensus" in title_lower):
        return "statement"

    if _has_summary_statements(pages):
        if (
            "research statement" in title_lower
            or "official" in title_lower and "statement" in title_lower
            or any(marker in title_lower for marker in STATEMENT_TITLE_MARKERS)
        ):
            return "statement"

    if recommendations:
        return "guideline"

    if looks_like_guideline(pages, sections, recommendations, raw_recommendations):
        return "guideline"

    if _has_recommendation_grade_signal(pages, sections):
        return "guideline"

    if _has_recommendations_heading(pages, sections):
        return "guideline"

    if looks_like_classification_update(pages, title_value):
        if "statement" in title_lower:
            return "statement"
        return "classification"

    if looks_like_statement(pages, title_value, sections):
        return "statement"

    if isinstance(title_info, dict):
        if title_lower and any(marker in title_lower for marker in GUIDELINE_TITLE_MARKERS):
            LOGGER.debug("Guideline detected via title marker.")
            return "guideline"

    first_page = pages[0] if pages else None
    if first_page:
        header_text = " ".join(line.strip() for line in (first_page.lines or [])[:25]).lower()
        if header_text and _contains_marker(header_text, GUIDELINE_FIRST_PAGE_MARKERS):
            LOGGER.debug("Guideline detected via first-page header markers.")
            return "guideline"

    anchor_hits = _count_recommendation_anchors(pages)
    if anchor_hits >= 6:
        LOGGER.debug("Guideline detected via recommendation anchors (hits=%d).", anchor_hits)
        return "guideline"

    first_page = pages[0] if pages else None
    if first_page:
        banner_text = " ".join(first_page.lines or []) or first_page.text or ""
        banner_hits = _count_grade_banner_hits(banner_text)
        if banner_hits >= 5:
            LOGGER.debug("Guideline retained via grade banners on first page (hits=%d).", banner_hits)
            return "guideline"

    if title_lower and any(marker in title_lower for marker in CLASSIFICATION_TITLE_MARKERS):
        LOGGER.debug("Classification detected via title marker.")
        return "classification"
    if title_lower and "statement" in title_lower and "american thoracic society" in title_lower:
        LOGGER.debug("Statement detected via title markers.")
        return "statement"

    if title_lower and any(marker in title_lower for marker in REVIEW_MARKERS):
        LOGGER.debug("Review detected from title marker.")
        return "review"

    for heading in sections.keys():
        if heading and any(marker in heading.lower() for marker in REVIEW_MARKERS):
            LOGGER.debug("Review detected from section heading '%s'.", heading)
            return "review"

    if recommendations:
        LOGGER.debug("Defaulting to research despite recommendations (guideline heuristics failed).")
    return "research"


def _recommendation_heading_hits(pages: Sequence[PageData]) -> int:
    hits = 0
    for page in pages[:8]:
        for heading in getattr(page, "headings", []):
            title = (heading.title or "").strip().lower()
            if not title:
                continue
            if any(token in title for token in GUIDELINE_HEADING_TOKENS):
                hits += 1
                break
    return hits


def _count_recommendation_anchors(pages: Sequence[PageData]) -> int:
    hits = 0
    for page in pages:
        content = page.text or " ".join(page.lines or [])
        if not content:
            continue
        hits += len(RECOMMENDATION_ANCHORS_PATTERN.findall(content))
        if hits >= 6:
            break
    return hits


def _contains_marker(text: str, markers: Sequence[str]) -> bool:
    for marker in markers:
        marker = marker.strip()
        if not marker:
            continue
        if " " in marker:
            if marker in text:
                return True
        else:
            if re.search(rf"\b{re.escape(marker)}\b", text):
                return True
    return False


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
