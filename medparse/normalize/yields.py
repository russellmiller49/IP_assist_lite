"""Diagnostic yield normalization utilities following ATS guidance."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple

STRICT_EXCLUSIONS = ("atypia", "suspicious", "nonspecific inflammation", "inflammation")
DIAGNOSTIC_YIELD_RE = re.compile(
    r"(?:overall\s+)?diagnostic\s+yield(?:\s*(?:was|=))?\s*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
FRACTION_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*(diagnostic|positive)", re.IGNORECASE)
PATIENT_COUNT_RE = re.compile(r"\b(\d+)\s+(patients|subjects|cases)\b", re.IGNORECASE)
LESION_COUNT_RE = re.compile(r"\b(\d+)\s+(lesions|nodules)\b", re.IGNORECASE)


def compute_strict_yield(categories: Sequence[Tuple[str, int]], denominator: int) -> dict:
    """Compute strict diagnostic yield by filtering vague categories."""

    numerator = sum(count for label, count in categories if _is_strict_positive(label))
    strict_yield = (numerator / denominator) if denominator else None
    return {
        "strict_numerator": numerator,
        "strict_denominator": denominator,
        "strict_yield": strict_yield,
    }


def yield_from_text(blocks: Iterable[str]) -> dict:
    """Parse narrative text for study-level yield and cohort counts."""

    n_patients = _first_match(blocks, PATIENT_COUNT_RE)
    n_lesions = _first_match(blocks, LESION_COUNT_RE)
    yield_pct = _first_match(blocks, DIAGNOSTIC_YIELD_RE)

    fraction = _first_fraction(blocks)
    if fraction and not yield_pct:
        numerator, denominator = fraction
        yield_pct = (numerator / denominator) * 100 if denominator else None

    return {
        "n_patients": n_patients,
        "n_lesions": n_lesions,
        "diagnostic_yield_pct": yield_pct,
        "diagnostic_yield_fraction": fraction,
    }


def _is_strict_positive(label: str) -> bool:
    lowered = label.lower()
    return not any(term in lowered for term in STRICT_EXCLUSIONS)


def _first_match(blocks: Iterable[str], pattern: re.Pattern) -> Optional[float]:
    for block in blocks:
        match = pattern.search(block)
        if match:
            try:
                return float(match.group(1))
            except (TypeError, ValueError):
                continue
    return None


def _first_fraction(blocks: Iterable[str]) -> Optional[Tuple[int, int]]:
    for block in blocks:
        match = FRACTION_RE.search(block)
        if match:
            num, denom = int(match.group(1)), int(match.group(2))
            return num, denom
    return None


__all__ = ["compute_strict_yield", "yield_from_text"]
