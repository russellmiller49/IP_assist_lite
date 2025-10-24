"""Routes documents to the appropriate extractor."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from medparse.schema.article import ArticleDocument
from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument
from medparse.schema.textbook import TextbookChapterDocument

from .articles import extract_article
from .ifu import extract_ifu
from .textbook import extract_textbook_chapter

DocType = Literal["article", "ifu", "textbook_chapter"]


def dispatch(pdf_path: Path, doc_type: DocType) -> BaseDocument:
    """Dispatch ``pdf_path`` to the extractor matching ``doc_type``."""

    if doc_type == "article":
        return extract_article(pdf_path)
    if doc_type == "ifu":
        return extract_ifu(pdf_path)
    if doc_type == "textbook_chapter":
        return extract_textbook_chapter(pdf_path)
    raise ValueError(f"Unsupported doc_type: {doc_type}")


__all__ = ["dispatch", "DocType"]
