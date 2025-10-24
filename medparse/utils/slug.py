"""Slug helpers to produce stable identifiers and filenames."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# Common typo corrections observed in upstream document naming.
TOKEN_REWRITES = {
    "cyrobiopsy": "cryobiopsy",
    "bronchscopy": "bronchoscopy",
    "endobronchail": "endobronchial",
}


def _normalize_token(token: str) -> str:
    token = TOKEN_REWRITES.get(token, token)
    return token


def slugify(text: str, *, delimiter: str = "-") -> str:
    """Normalize free-form text into a lowercase slug.

    Accents are stripped, punctuation collapsed, and common typos rewritten to
    keep file identifiers stable across ingestion runs.
    """

    if not text:
        return ""

    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    tokens = [_normalize_token(tok) for tok in re.split(r"[^a-z0-9]+", lowered) if tok]
    return delimiter.join(tokens)


def ensure_unique_slug(base: str, existing: Iterable[str]) -> str:
    """Mint a slug that does not collide with an existing collection."""

    base_slug = slugify(base)
    if base_slug and base_slug not in existing:
        return base_slug
    counter = 2
    while True:
        candidate = f"{base_slug}-{counter}" if base_slug else str(counter)
        if candidate not in existing:
            return candidate
        counter += 1


__all__ = ["slugify", "ensure_unique_slug"]
