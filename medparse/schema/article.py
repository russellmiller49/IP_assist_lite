"""Schemas for research articles and clinical studies."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import Field

from .base import MedparseModel
from .common import BaseDocument, EvidenceSpan


class Outcome(MedparseModel):
    """Individual study outcome such as complications or performance metrics."""

    name: str
    value: Optional[float] = None
    unit: Optional[str] = None
    evidence: Optional[EvidenceSpan] = None


class YieldSummary(MedparseModel):
    """Strict diagnostic yield summary following ATS guidance."""

    strict_numerator: Optional[int] = Field(default=None, ge=0)
    strict_denominator: Optional[int] = Field(default=None, ge=0)
    strict_yield: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = None
    evidence: Optional[EvidenceSpan] = None


class ArticleDocument(BaseDocument):
    """Structured representation of a research article extraction."""

    doc_type: Literal["article"] = Field(default="article", frozen=True)
    title: Optional[str] = None
    abstract: Optional[str] = None
    year: Optional[int] = None
    n_patients: Optional[int] = Field(default=None, ge=0)
    n_lesions: Optional[int] = Field(default=None, ge=0)
    outcomes: List[Outcome] = Field(default_factory=list)
    yield_summary: Optional[YieldSummary] = None
    tables: list = Field(default_factory=list)
    references: list = Field(default_factory=list)
