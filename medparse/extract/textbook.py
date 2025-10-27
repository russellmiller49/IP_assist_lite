"""Backward-compatible import wrapper for the legacy module path."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from medparse.config import ExtractionConfig, get_extraction_config
from medparse.extractors.textbook import extract_textbook_chapter as _extract_textbook_chapter
from medparse.ingest.models import PageData
from medparse.schema.textbook import TextbookChapterDocument


def extract_textbook_chapter(
    pdf_path: Path,
    *,
    engine: str = "fitz",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
    config: Optional[ExtractionConfig] = None,
) -> TextbookChapterDocument:
    """Delegate to the profile-aware textbook extractor."""

    extraction_config = config or get_extraction_config()
    return _extract_textbook_chapter(
        pdf_path,
        engine=engine,
        page_limit=page_limit,
        pages=pages,
        config=extraction_config,
    )


__all__ = ["extract_textbook_chapter"]
