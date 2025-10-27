"""Backward-compatible import wrapper for the legacy module path."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from medparse.config import ExtractionConfig, get_extraction_config
from medparse.extractors.article import extract_article as _extract_article
from medparse.ingest.models import PageData
from medparse.schema.article import ArticleDocument


def extract_article(
    pdf_path: Path,
    *,
    engine: str = "fitz",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
    config: Optional[ExtractionConfig] = None,
) -> ArticleDocument:
    """Delegate to the profile-aware extractor."""

    extraction_config = config or get_extraction_config()
    return _extract_article(
        pdf_path,
        engine=engine,
        page_limit=page_limit,
        pages=pages,
        config=extraction_config,
    )


__all__ = ["extract_article"]
