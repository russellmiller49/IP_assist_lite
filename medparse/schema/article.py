"""Schemas for research articles and clinical studies."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Tuple

from pydantic import Field

from .base import MedparseModel
from .common import BaseDocument, EvidenceSpan, Relation, UmlsEntity


class Author(MedparseModel):
    """Author with structured name, ORCID, email, and affiliation links."""

    given: str
    family: str
    suffix: Optional[str] = None
    orcid: Optional[str] = None
    email: Optional[str] = None
    affiliation_ids: List[str] = Field(default_factory=list)
    is_corresponding: bool = False
    footnote_symbols: List[str] = Field(default_factory=list)  # †, ‡, *, etc.
    equal_contribution: bool = False


class Affiliation(MedparseModel):
    """Institutional affiliation with unique ID."""

    id: str  # e.g., "1", "a", "aff1"
    text: str
    department: Optional[str] = None
    institution: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    address: Optional[str] = None


class GrantInfo(MedparseModel):
    """Funding grant with agency and number."""

    agency: str
    grant_number: Optional[str] = None
    recipient: Optional[str] = None  # Author name if specified


class Outcome(MedparseModel):
    """Individual study outcome such as complications or performance metrics."""

    name: str
    value: Optional[float] = None
    n: Optional[int] = None
    percent: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    denominator: Optional[int] = None
    grade: Optional[str] = None  # CTCAE grade for adverse events
    time_window: Optional[str] = None  # e.g., "30-day", "in-hospital"
    footnotes: List[str] = Field(default_factory=list)
    inconclusive: bool = False
    linked_figure_table: Optional[str] = None
    evidence: Optional[EvidenceSpan] = None
    evidence_refs: Optional[List[str]] = None  # Hash IDs for evidence bank


class DiagnosticYield(MedparseModel):
    """ATS-compliant diagnostic yield with denominator provenance."""

    value: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    reported_value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    lower_ci: Optional[float] = None
    upper_ci: Optional[float] = None
    numerator: Optional[int] = Field(default=None, ge=0)
    denominator: Optional[int] = Field(default=None, ge=0)
    denominator_type: Optional[Literal["enrolled", "biopsied", "lesions"]] = None
    exclusion_reasons: List[str] = Field(default_factory=list)
    method_note: Optional[str] = None
    evidence_refs: Optional[List[str]] = None  # Hash IDs for evidence bank
    pooled_value: Optional[float] = None  # When multiple strata pooled
    pooling_method: Optional[Literal["fixed_effects", "weighted"]] = None
    strata: List[Dict] = Field(default_factory=list)  # Individual stratum yields
    compatible_with_ats: bool = False
    strict: bool = True
    evidence: Optional[EvidenceSpan] = None
    denominator_hint: Optional[str] = None

    @property
    def strict_yield(self) -> Optional[float]:
        if self.value is None:
            return None
        return self.value / 100.0

    @property
    def strict_numerator(self) -> Optional[int]:
        return self.numerator

    @property
    def strict_denominator(self) -> Optional[int]:
        return self.denominator


class GuidelineRecommendation(MedparseModel):
    """Guideline recommendation with grade, strength, and statement type."""

    label: Optional[str] = None  # e.g., "1", "1.1", "A"
    text: str
    grade: Optional[str] = None  # Normalized grade token when available
    grade_raw: Optional[str] = None  # Raw grade string from source text
    strength: Optional[str] = None  # Normalized: "strong", "weak", "conditional"
    strength_scale: Optional[str] = None  # Scale name e.g., GRADE, ACCP
    evidence_level: Optional[str] = None  # Level I-IV or High/Moderate/Low
    statement_type: Literal["graded", "consensus", "good_practice", "ungraded"] = "graded"
    votes: Optional[str] = None  # e.g., "15/17 agreed"
    consensus_percentage: Optional[float] = None
    page_span: Optional[Tuple[int, int]] = None
    evidence: Optional[EvidenceSpan] = None
    evidence_refs: Optional[List[str]] = None  # Hash IDs for evidence bank
    normalized: Optional[Dict[str, Optional[str]]] = None  # {strength, quality, scale}
    anchors: List[str] = Field(default_factory=list)


class KeyPoint(MedparseModel):
    """Structured key point extracted from summary statements."""

    id: str
    text: str
    page: Optional[int] = None
    evidence: Optional[EvidenceSpan] = None
    evidence_refs: Optional[List[str]] = None


class DiagnosticFlow(MedparseModel):
    """Representation of diagnostic flow definition (e.g., ATS STARD figure)."""

    formula: Optional[str] = None
    notes: Optional[str] = None
    evidence: Optional[EvidenceSpan] = None
    evidence_refs: Optional[List[str]] = None


class TableFootnote(MedparseModel):
    """Table footnote with symbol and text."""

    symbol: str  # *, †, ‡, a, b, etc.
    text: str


class EnhancedTable(MedparseModel):
    """Table with header stitching, stub columns, and footnotes."""

    id: str
    label: Optional[str] = None  # "Table 1", "Table 2a"
    caption: Optional[str] = None
    headers: List[List[str]] = Field(default_factory=list)  # Multi-row headers
    stub_column: Optional[int] = None  # Index of stub/row-header column
    rows: List[List[str]] = Field(default_factory=list)
    footnotes: List[TableFootnote] = Field(default_factory=list)
    page: Optional[int] = None
    table_type: Optional[str] = None  # From classifier
    truncated_cells: bool = False


class ArticleFigure(MedparseModel):
    """Figure with caption metadata."""

    label: str
    caption: Optional[str] = None
    page: Optional[int] = None


class AuthorInfo(MedparseModel):
    """Legacy author info for backward compatibility."""

    name: str
    affiliation: Optional[str] = None
    email: Optional[str] = None


class ArticleDocument(BaseDocument):
    """Structured representation of a research article extraction."""

    doc_type: Literal["article"] = Field(default="article", frozen=True)
    doc_subtype: Optional[
        Literal["guideline", "research", "review", "statement", "classification"]
    ] = None

    # Title and metadata (enhanced)
    title: Optional[str] = None
    subtitle: Optional[str] = None
    title_source: Optional[str] = None  # 'layout', 'metadata', 'doi', 'header'
    title_confidence: float = 0.0
    doi: Optional[str] = None
    pmid: Optional[str] = None
    issn: Optional[str] = None
    url: Optional[str] = None

    # Authors and affiliations (enhanced)
    authors: List[Author] = Field(default_factory=list)
    affiliations: List[Affiliation] = Field(default_factory=list)
    group_authors: List[str] = Field(default_factory=list)  # "on behalf of X Consortium"

    # Publication info
    journal: Optional[str] = None
    year: Optional[int] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None

    # Content (enhanced)
    abstract: Optional[str] = None
    graphical_abstract_image: Optional[str] = None  # Path or base64
    highlights: List[str] = Field(default_factory=list)  # "What this paper adds", "Key Points"
    keywords: List[str] = Field(default_factory=list)
    sections: Dict[str, str] = Field(default_factory=dict)  # section_name -> text
    key_points: List[KeyPoint] = Field(default_factory=list)

    # Study data
    n_patients: Optional[int] = Field(default=None, ge=0)
    n_lesions: Optional[int] = Field(default=None, ge=0)

    # Outcomes (enhanced)
    outcomes: List[Outcome] = Field(default_factory=list)
    diagnostic_yield: Optional[DiagnosticYield] = None
    definitions: Dict[str, str] = Field(default_factory=dict)
    definitions_evidence: Optional[EvidenceSpan] = None
    definitions_evidence_refs: Optional[List[str]] = None
    diagnostic_flow: Optional[DiagnosticFlow] = None
    yield_definitions_present: Optional[bool] = None

    # Guidelines (enhanced)
    recommendations: List[GuidelineRecommendation] = Field(default_factory=list)

    # Disclosures (enhanced)
    conflicts_of_interest: List[str] = Field(default_factory=list)
    has_no_conflicts: bool = False  # True when "authors declare no competing interests"
    funding_sources: List[GrantInfo] = Field(default_factory=list)
    has_no_funding: bool = False  # True when "no funding received"

    # Structured data (enhanced)
    tables: List[EnhancedTable] = Field(default_factory=list)
    figures: List[ArticleFigure] = Field(default_factory=list)
    references: list = Field(default_factory=list)
    umls_entities: List[UmlsEntity] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)

    # Legacy compatibility
    @property
    def yield_summary(self) -> Optional[DiagnosticYield]:
        """Backward compatibility alias."""
        return self.diagnostic_yield

    @property
    def corresponding_author(self) -> Optional[Author]:
        """Get first corresponding author for backward compatibility."""
        corresponding = [a for a in self.authors if a.is_corresponding]
        return corresponding[0] if corresponding else None
