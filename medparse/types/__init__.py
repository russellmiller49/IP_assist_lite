"""Typed document schemas and primitives for Medparse."""

from .base import (
    BaseDocument,
    EvidenceSpan,
    Figure,
    IFUWarning,
    Relation,
    Section,
    StatResult,
    Table,
    TableCell,
)
from .book import BookChapterDocument
from .guideline import GuidelineDocument
from .ifu import IFUDocument
from .research import ResearchDocument

__all__ = [
    "BaseDocument",
    "EvidenceSpan",
    "Section",
    "Figure",
    "Table",
    "TableCell",
    "StatResult",
    "Relation",
    "IFUWarning",
    "IFUDocument",
    "GuidelineDocument",
    "ResearchDocument",
    "BookChapterDocument",
]
