"""Schemas for textbook chapter extraction."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import Field

from .base import MedparseModel
from .common import BaseDocument, EvidenceSpan


class Section(MedparseModel):
    """Textbook section with paragraphs and supporting evidence span."""

    title: str
    paragraphs: List[str] = Field(default_factory=list)
    evidence: EvidenceSpan


class BookMeta(MedparseModel):
    """Metadata applied uniformly across textbook chapters."""

    book_title: str
    edition: Optional[str] = None
    editors: List[str] = Field(default_factory=list)
    publisher: Optional[str] = None
    isbn: Optional[str] = None
    year: Optional[int] = None


class TextbookChapterDocument(BaseDocument):
    """Structured representation of a textbook chapter."""

    doc_type: Literal["textbook_chapter"] = Field(default="textbook_chapter", frozen=True)
    chapter_title: str
    chapter_number: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    abstract: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    sections: List[Section] = Field(default_factory=list)
    book_meta: Optional[BookMeta] = None
