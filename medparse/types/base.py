"""Base Pydantic models and helpers shared across document schemas."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

DEFAULT_EXTRACTION_VERSION = "v3.0.0"


def _stable_id(prefix: str, *components: Any) -> str:
    """Return a deterministic identifier based on the provided components."""

    material = "::".join(str(component) for component in components if component is not None)
    digest = hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


class EvidenceSpan(BaseModel):
    """Represents a traceable evidence span from the source document."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    page: int
    bbox_norm: Optional[Tuple[float, float, float, float]] = None  # Normalised [0,1] coords
    text: str
    confidence: float = 1.0
    bbox: Optional[Tuple[float, float, float, float]] = None  # Legacy absolute coords

    @field_validator("bbox_norm")
    def _validate_bbox_norm(
        cls, value: Optional[Tuple[float, float, float, float]]
    ) -> Optional[Tuple[float, float, float, float]]:
        if value is None:
            return value
        if len(value) != 4:
            raise ValueError("bbox_norm must contain four float values.")
        for coordinate in value:
            if coordinate is None:
                raise ValueError("bbox_norm values must be floats.")
            if not 0.0 <= coordinate <= 1.0:
                raise ValueError("bbox_norm values must lie within [0, 1].")
        return value


class Section(BaseModel):
    """Structured section with provenance and optional callouts."""

    id: str
    title: Optional[str] = None
    level: Optional[int] = None
    text: str
    page_anchor: Optional[int] = None
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TableCell(BaseModel):
    """Single table cell with position metadata."""

    row: int
    col: int
    text: str


class Table(BaseModel):
    """Structured table representation with caption, provenance and cell detail."""

    id: str
    label: Optional[str] = None
    caption: str
    page: int
    bbox_norm: Tuple[float, float, float, float]
    cells: Optional[List[TableCell]] = None
    html: Optional[str] = None
    csv: Optional[str] = None
    image_path: Optional[str] = None
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list)


class Figure(BaseModel):
    """Structured figure representation with caption, provenance and crop path."""

    id: str
    label: Optional[str] = None
    caption: str
    page: int
    bbox_norm: Tuple[float, float, float, float]
    image_path: str
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list)


class StatResult(BaseModel):
    """Structured statistical result with evidence traceability."""

    model_config = ConfigDict(extra="ignore")

    id: str
    kind: str = Field(validation_alias=AliasChoices("type", "kind"))
    value: Optional[float] = None
    unit: Optional[str] = None
    context: Optional[str] = None
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list)


class Relation(BaseModel):
    """Graph relation linking document entities together."""

    id: str
    subject_id: str
    predicate: Literal["SUPPORTED_BY", "MENTIONS", "DERIVED_FROM"]
    object_id: str
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list)


class IFUWarning(BaseModel):
    """Model for warnings/cautions/notes with provenance."""

    id: str
    severity: Literal["warning", "caution", "note"]
    category: Optional[str] = None
    text: str
    page: int
    bbox_norm: Tuple[float, float, float, float]
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list)


class BaseDocument(BaseModel):
    """Common metadata shared by all document outputs."""

    doc_id: str = Field(default_factory=lambda: str(uuid4()))
    doc_type: Literal["ifu", "guideline", "research", "book_chapter"]
    source_file: str
    page_count: Optional[int] = None
    extraction_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extraction_version: str = DEFAULT_EXTRACTION_VERSION
    title: Optional[str] = None
    sections: List[Section] = Field(default_factory=list)
    figures: List[Figure] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    stats: List[StatResult] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    warnings: List[IFUWarning] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def stable_id(self, prefix: str, *components: Any) -> str:
        """Helper to create deterministic IDs bound to this document."""

        return _stable_id(prefix, self.doc_id, *components)
