"""Stable hashing and normalization helpers for paragraph text."""

from __future__ import annotations

import re
import unicodedata
from hashlib import blake2b
from typing import Final

from .normalize_punct import normalize_punctuation

_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")


def normalize_paragraph_text(text: str | None) -> str:
    """Normalize paragraph text with Unicode folding and whitespace collapse."""

    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalize_punctuation(normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()


def stable_par_hash(doc_id: str, page: int | None, text: str | None) -> str:
    """Compute a stable paragraph hash using document ID, page, and normalized text."""

    normalized = normalize_paragraph_text(text)
    page_part = str(page if page is not None else -1)
    payload = f"{doc_id}|{page_part}|{normalized}"
    return blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()


__all__ = ["stable_par_hash", "normalize_paragraph_text"]
