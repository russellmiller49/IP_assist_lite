"""Diagnostic yield data models."""

from typing import Optional

from pydantic import BaseModel

from .base import EvidenceSpan


class DiagnosticYieldStrict(BaseModel):
    """ATS 2024 strict yield definition."""

    numerator: int
    denominator: int
    yield_pct: float
    evidence: Optional[EvidenceSpan] = None


class NondiagnosticCounts(BaseModel):
    """Breakdown of nondiagnostic findings that must be excluded from yield."""

    atypia_or_suspicious: int = 0
    nonspecific_inflammation: int = 0
    other_nondiagnostic: int = 0
