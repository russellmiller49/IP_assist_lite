"""Punctuation and URL spacing normalization helpers."""

from __future__ import annotations

import re

URL_WITH_SPACES = re.compile(
    r"\b((?:https?|ftp)\s*://\s*)?((?:www)\s*(?:\.\s*[A-Za-z0-9_-]+){1,})",
    re.IGNORECASE,
)
WWW_WITH_COLON = re.compile(r"\bwww\s*:\s*", re.IGNORECASE)
EMAIL_WITH_SPACES = re.compile(r"\b([\w.+-]+)\s*@\s*([\w.-]+\.\w+)\b")
DOUBLE_SPACE_AFTER_PERIOD = re.compile(r"\.(\s{2,})")


def _collapse_dot_sequence(sequence: str) -> str:
    parts = re.split(r"\s*\.\s*", sequence.strip())
    parts = [part for part in parts if part]
    return ".".join(parts)


def normalize_punctuation(text: str | None) -> str:
    """Normalize spaced punctuation in URLs/emails and tidy stray whitespace."""

    if not text:
        return ""

    normalized = WWW_WITH_COLON.sub("www.", text)

    def _replace_url(match: re.Match[str]) -> str:
        prefix = match.group(1) or ""
        sequence = match.group(2)
        collapsed = _collapse_dot_sequence(sequence)
        return f"{prefix}{collapsed}"

    normalized = URL_WITH_SPACES.sub(_replace_url, normalized)
    normalized = EMAIL_WITH_SPACES.sub(r"\1@\2", normalized)
    normalized = DOUBLE_SPACE_AFTER_PERIOD.sub(". ", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    return normalized


__all__ = ["normalize_punctuation"]
