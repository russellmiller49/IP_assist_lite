"""Schemas for Instructions for Use documents."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .base import BaseDocument, EvidenceSpan, IFUWarning


class IFUSectionEntry(BaseModel):
    """Structured IFU section content with evidence traceability."""

    id: str
    text: str
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @property
    def evidence(self) -> Optional[EvidenceSpan]:
        """Backwards compatible accessor for the first evidence span."""

        return self.evidence_spans[0] if self.evidence_spans else None


class IFUDocument(BaseDocument):
    """Top-level IFU document payload."""

    manufacturer: Optional[str] = None
    model: Optional[str] = None
    indications_for_use: List[IFUSectionEntry] = Field(default_factory=list)
    intended_use: List[IFUSectionEntry] = Field(default_factory=list)
    contraindications: List[IFUSectionEntry] = Field(default_factory=list)
    intended_user: Optional[str] = None
    references: List[dict] = Field(default_factory=list)
    warning_index: dict[str, List[str]] = Field(default_factory=dict)

    def add_warning(self, warning: IFUWarning) -> None:
        """Append `warning` and update severity index."""

        self.warnings.append(warning)
        self.warning_index.setdefault(warning.severity, []).append(warning.id)
