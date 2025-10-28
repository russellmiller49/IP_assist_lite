"""Shared schema utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple
from uuid import uuid4

from pydantic import Field

from .base import MedparseModel


class EvidenceSpan(MedparseModel):
    """Snippet of source evidence with optional layout context."""

    text: str
    page: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    truncated: bool = False


class BaseDocument(MedparseModel):
    """Base document metadata shared across extraction modes."""

    doc_id: str = Field(default_factory=lambda: str(uuid4()))
    doc_type: Literal["article", "ifu", "textbook_chapter"]
    source_file: str
    page_count: Optional[int] = None
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    extraction_version: str = "v1.0.0"
    pipeline_info: Dict[str, object] = Field(default_factory=dict, exclude=True)


class UmlsEntity(MedparseModel):
    """Linked UMLS entity with offsets on the source text."""

    cui: str
    preferred_term: Optional[str] = None
    semtypes: List[str] = Field(default_factory=list)
    offsets: List[Tuple[int, int]] = Field(default_factory=list)
    text: str
    page: Optional[int] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Relation(MedparseModel):
    """Normalized relation triple with optional attributes."""

    subject: str
    predicate: str
    object: str
    attributes: Dict[str, object] = Field(default_factory=dict)
    evidence: Optional[EvidenceSpan] = None


__all__ = ["EvidenceSpan", "BaseDocument", "UmlsEntity", "Relation"]
