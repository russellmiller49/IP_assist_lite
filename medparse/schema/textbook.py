"""Schemas for textbook chapter extraction."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import Field

from .base import MedparseModel
from .common import BaseDocument, EvidenceSpan, Relation, UmlsEntity


class Section(MedparseModel):
    """Textbook section with paragraphs and supporting evidence span."""

    title: str
    paragraphs: List[str] = Field(default_factory=list)
    evidence: EvidenceSpan


class SectionMetadata(MedparseModel):
    """Enhanced section with page span and numbering."""

    text: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    number: Optional[str] = None  # e.g., "2.1", "2.1.1"


class BookMeta(MedparseModel):
    """Metadata applied uniformly across textbook chapters."""

    book_title: str
    edition: Optional[str] = None
    editors: List[str] = Field(default_factory=list)
    publisher: Optional[str] = None
    isbn: Optional[str] = None
    year: Optional[int] = None
    book_doi: Optional[str] = None


class AuthorInfo(MedparseModel):
    """Chapter author with affiliation."""

    name: str
    affiliation: Optional[str] = None
    email: Optional[str] = None


class FigureInfo(MedparseModel):
    """Figure with caption."""

    label: str  # e.g., "Figure 1", "Fig. 2a"
    caption: Optional[str] = None
    page: Optional[int] = None


class TextbookChapterDocument(BaseDocument):
    """Structured representation of a textbook chapter."""

    doc_type: Literal["textbook_chapter"] = Field(default="textbook_chapter", frozen=True)

    # Chapter identification
    chapter_title: str
    chapter_number: Optional[str] = None
    chapter_doi: Optional[str] = None

    # Authors (enhanced with affiliations)
    chapter_authors: List[AuthorInfo] = Field(default_factory=list)
    corresponding_author: Optional[AuthorInfo] = None

    # Content
    abstract: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)

    # Sections (enhanced with page spans)
    sections: Dict[str, SectionMetadata] = Field(default_factory=dict)

    # Visual elements
    figures: List[FigureInfo] = Field(default_factory=list)
    tables: List[dict] = Field(default_factory=list)

    # Book-level metadata
    book_meta: Optional[BookMeta] = None

    umls_entities: List[UmlsEntity] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    coverage_ratio: Optional[float] = Field(default=None)

    # For backward compatibility
    @property
    def authors(self) -> List[str]:
        """Legacy authors property for backward compatibility."""
        return [a.name for a in self.chapter_authors]
