"""Structured table representations."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from .base import EvidenceSpan


class TableCell(BaseModel):
    """Represents a single table cell."""

    text: str
    row: int
    col: int
    span: Optional[EvidenceSpan] = None


class Table(BaseModel):
    """Normalized table with optional semantic type."""

    title: Optional[str] = None
    type: Optional[str] = None
    headers: List[str]
    rows: List[List[str]]
    evidence: Optional[EvidenceSpan] = None
    metadata: Dict[str, Any] = {}
