"""Shared schema utilities."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple
from uuid import uuid4

from pydantic import Field

from .base import MedparseModel


class EvidenceSpan(MedparseModel):
    """Snippet of source evidence with optional layout context.

    ``text`` is optional so we can emit compact pointers that reference a shared
    ``evidence_bank`` entry by ``hash``.
    """

    text: Optional[str] = None
    hash: Optional[str] = None
    page: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    truncated: bool = False
    paragraph_hash: Optional[str] = None
    paragraph_offset: Optional[Tuple[int, int]] = None

    def compute_hash(self, max_chars: int = 2000) -> str:
        """Compute stable hash for deduplication.

        Args:
            max_chars: Maximum text length to include in hash

        Returns:
            SHA-1 hash as hex string
        """
        if self.hash:
            return self.hash

        text_trimmed = (self.text or "")[:max_chars]
        bbox_str = f"{self.bbox}" if self.bbox else ""
        key = f"{self.page or 0}:{bbox_str}:{text_trimmed}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def as_pointer(self) -> "EvidenceSpan":
        """Return a copy suitable for emission (no inline text)."""

        return EvidenceSpan(
            hash=self.hash,
            page=self.page,
            bbox=self.bbox,
            confidence=self.confidence,
            truncated=self.truncated,
            paragraph_hash=self.paragraph_hash,
            paragraph_offset=self.paragraph_offset,
        )


class SizeGuards(MedparseModel):
    """Configuration for output size limits and truncation."""

    max_evidence_per_item: int = 3
    max_chars_per_evidence: int = 1200
    max_tables: int = 50
    max_table_cells: int = 5000
    max_sections: int = 60
    max_paragraph_chars: int = 2000
    keep_table_types: List[str] = Field(
        default_factory=lambda: [
            "diagnostic_accuracy",
            "baseline",
            "complications",
            "yield",
            "outcomes",
        ]
    )


class TruncationNotice(MedparseModel):
    """Record of content truncated due to size guards."""

    evidence_dropped: int = 0
    tables_dropped: int = 0
    sections_dropped: int = 0
    chars_truncated: int = 0
    reason: str = "size_guards"


class BaseDocument(MedparseModel):
    """Base document metadata shared across extraction modes."""

    doc_id: str = Field(default_factory=lambda: str(uuid4()))
    doc_type: Literal["article", "ifu", "textbook_chapter"]
    source_file: str
    page_count: Optional[int] = None
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    extraction_version: str = "v1.0.0"
    pipeline_info: Dict[str, object] = Field(default_factory=dict, exclude=True)

    # Evidence deduplication
    evidence_bank: Dict[str, EvidenceSpan] = Field(
        default_factory=dict,
        description="Central store of deduplicated evidence spans, keyed by hash",
    )
    paragraph_store: Dict[str, str] = Field(
        default_factory=dict,
        description="Deduplicated paragraph text keyed by stable hash",
    )
    truncation_notice: Optional[TruncationNotice] = None
    front_matter_source: Optional[str] = None
    front_matter_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


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
    evidence_refs: Optional[List[str]] = None  # Hash IDs for evidence bank


__all__ = [
    "EvidenceSpan",
    "BaseDocument",
    "SizeGuards",
    "TruncationNotice",
    "UmlsEntity",
    "Relation",
]
