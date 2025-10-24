"""Compatibility wrapper for legacy imports."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from medparse.extractors.ifu import extract_ifu as _extract_ifu
from medparse.ingest.models import PageData
from medparse.schema.ifu import IFUDocument


def extract_ifu(
    pdf_path: Path,
    *,
    engine: str = "pymupdf",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
) -> IFUDocument:
    return _extract_ifu(pdf_path, engine=engine, page_limit=page_limit, pages=pages)


__all__ = ["extract_ifu"]
