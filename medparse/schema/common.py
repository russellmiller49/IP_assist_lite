"""Shared schema utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Tuple
from uuid import uuid4

from pydantic import Field

from .base import MedparseModel


class EvidenceSpan(MedparseModel):
    """Snippet of source evidence with optional layout context."""

    text: str
    page: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class BaseDocument(MedparseModel):
    """Base document metadata shared across extraction modes."""

    doc_id: str = Field(default_factory=lambda: str(uuid4()))
    doc_type: Literal["article", "ifu", "textbook_chapter"]
    source_file: str
    page_count: Optional[int] = None
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    extraction_version: str = "v1.0.0"


__all__ = ["EvidenceSpan", "BaseDocument"]
