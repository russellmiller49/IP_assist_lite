"""Schemas for guideline documents."""

from typing import List, Optional

from pydantic import BaseModel, Field

from .base import BaseDocument, EvidenceSpan


class GuidelineRecommendation(BaseModel):
    """A single guideline recommendation statement."""

    number: Optional[str] = None
    text: str
    grade: Optional[str] = None
    strength_scale: Optional[str] = None
    evidence_level: Optional[str] = None
    consensus_percentage: Optional[float] = None
    voting_results: Optional[str] = None
    figures: List[str] = Field(default_factory=list)
    evidence: EvidenceSpan


class GuidelineDocument(BaseDocument):
    """Top-level guideline payload."""

    society: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    recommendations: List[GuidelineRecommendation] = Field(default_factory=list)
