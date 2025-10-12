"""Routes classified documents to the appropriate extractor."""

from __future__ import annotations

from pathlib import Path

from medparse.classify.rules import classify_with_rules
from medparse.config import ExtractionConfig
from medparse.types import BaseDocument
from medparse.types.book import BookChapterDocument
from medparse.types.guideline import GuidelineDocument
from medparse.types.ifu import IFUDocument
from medparse.types.research import ResearchDocument

from .book import extract_book_chapter
from .guideline import extract_guideline
from .ifu import extract_ifu
from .research import extract_research


def dispatch_document(pdf_path: Path, config: ExtractionConfig | None = None) -> BaseDocument:
    """Classify ``pdf_path`` and dispatch to the matching extractor."""
    config = config or ExtractionConfig()
    doc_type = classify_with_rules(pdf_path)

    if doc_type == "ifu":
        return extract_ifu(pdf_path, config)
    if doc_type == "guideline":
        return extract_guideline(pdf_path, config)
    if doc_type == "book_chapter":
        return extract_book_chapter(pdf_path, config)
    if doc_type == "research":
        return extract_research(pdf_path, config)

    # Generic fallback when classification yields unsupported type
    return BaseDocument(doc_type="research", source_file=str(pdf_path))
