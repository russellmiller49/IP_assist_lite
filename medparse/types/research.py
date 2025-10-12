"""Schemas for research documents."""

from typing import List, Optional

from pydantic import BaseModel

from .base import BaseDocument, EvidenceSpan
from .yield_defs import DiagnosticYieldStrict, NondiagnosticCounts


class Outcome(BaseModel):
    """Structured representation of a reported outcome."""

    name: str
    value: Optional[float] = None
    unit: Optional[str] = None
    evidence: Optional[EvidenceSpan] = None


class ResearchDocument(BaseDocument):
    """Top-level research payload."""

    title: Optional[str] = None
    design: Optional[str] = None
    centers: Optional[str] = None
    n_patients: Optional[int] = None
    n_lesions: Optional[int] = None
    primary_outcome: Optional[str] = None
    outcomes: List[Outcome] = []
    ats_yield: Optional[DiagnosticYieldStrict] = None
    nondiagnostic: Optional[NondiagnosticCounts] = None
