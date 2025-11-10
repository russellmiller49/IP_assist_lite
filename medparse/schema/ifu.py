"""Schemas for Instructions for Use (IFU) manuals."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

from pydantic import Field

from .base import MedparseModel
from .common import BaseDocument, EvidenceSpan


class SafetyBlock(MedparseModel):
    """Represent a categorized safety block with evidence."""

    level: Literal["danger", "warning", "caution", "notice", "note", "attention"]
    text: str
    title: Optional[str] = None
    page: Optional[int] = None
    hash: Optional[str] = None
    severity: Optional[Literal["warning", "caution", "note"]] = None
    category: Optional[str] = None
    source: Optional[Literal["heading", "table", "icon"]] = None
    evidence: EvidenceSpan


class IFUDocument(BaseDocument):
    """Structured IFU/manual extraction."""

    doc_type: Literal["ifu"] = Field(default="ifu", frozen=True)
    doc_subtype: Optional[Literal["ifu", "catalog", "installation_guide", "tech_manual"]] = None
    manufacturer: Optional[str] = None
    product_name: Optional[str] = None
    part_number: Optional[str] = None
    revision: Optional[str] = None
    publication_date: Optional[str] = None
    model: Optional[str] = None
    software_versions: List[str] = Field(default_factory=list)
    indications_for_use: Optional[Union[str, Dict[str, object]]] = None
    intended_use: Optional[str] = None
    intended_user: Optional[str] = None
    intended_patient_population: Optional[str] = None
    contraindications: List[str] = Field(default_factory=list)
    adverse_events: List[str] = Field(default_factory=list)
    safety_blocks: List[SafetyBlock] = Field(default_factory=list)
    tables: list = Field(default_factory=list)
    references: list = Field(default_factory=list)
