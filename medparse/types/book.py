"""Schemas for book chapter documents."""

from typing import List

from pydantic import BaseModel

from .base import BaseDocument, EvidenceSpan


class Section(BaseModel):
    """Represents a section within a book chapter."""

    title: str
    paragraphs: List[str]
    evidence: EvidenceSpan


class BookChapterDocument(BaseDocument):
    """Structured representation of a book chapter."""

    title: str
    authors: List[str] = []
    sections: List[Section] = []
