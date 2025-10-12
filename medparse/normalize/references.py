"""Reference normalization helpers."""

from __future__ import annotations

from typing import Iterable, List

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - optional dependency
    fuzz = None  # type: ignore


def normalize_references(candidates: Iterable[str]) -> List[str]:
    """Filter and normalize bibliographic references."""
    normalized: List[str] = []
    for candidate in candidates:
        cleaned = candidate.strip()
        if not cleaned:
            continue
        if not _is_unique(cleaned, normalized):
            continue
        normalized.append(cleaned)
    return normalized


def _is_unique(candidate: str, existing: List[str]) -> bool:
    candidate_lower = candidate.lower()
    for item in existing:
        if candidate_lower == item.lower():
            return False
        if fuzz:
            if fuzz.token_set_ratio(candidate_lower, item.lower()) >= 92:
                return False
    return True
