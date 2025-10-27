"""Guideline extractor leveraging the article pipeline with guideline enrichers."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from medparse.config import ExtractionConfig, get_extraction_config
from medparse.extractors.article import extract_article
from medparse.ingest.models import PageData
from medparse.schema.article import ArticleDocument


def extract_guideline(
    pdf_path: Path,
    *,
    engine: str = "fitz",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
    config: Optional[ExtractionConfig] = None,
) -> ArticleDocument:
    """Extract a guideline document with guideline-specific enrichers enabled."""

    base_config = config or get_extraction_config()
    if not base_config.should_normalize_guidelines():
        guideline_config = base_config.model_copy(update={"enable_guideline_norms": True})
    else:
        guideline_config = base_config

    return extract_article(
        pdf_path,
        engine=engine,
        page_limit=page_limit,
        pages=pages,
        config=guideline_config,
    )


__all__ = ["extract_guideline"]

