"""Utilities for paragraph-level text processing and hashing."""

from __future__ import annotations

__all__ = [
    "Paragraph",
    "iter_paragraphs",
    "build_paragraph_store",
    "stable_par_hash",
    "normalize_paragraph_text",
    "is_boilerplate_line",
    "strip_boilerplate",
    "normalize_punctuation",
]

from .paragraphizer import Paragraph, iter_paragraphs, build_paragraph_store  # noqa: E402
from .hash import stable_par_hash, normalize_paragraph_text  # noqa: E402
from .headers import is_boilerplate_line, strip_boilerplate  # noqa: E402
from .normalize_punct import normalize_punctuation  # noqa: E402
