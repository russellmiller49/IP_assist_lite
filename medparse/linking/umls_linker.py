"""Core utilities for UMLS linking decisions."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple


def _overlap(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    """Return True when intervals overlap by at least one character (no touching)."""
    start_a, end_a = a
    start_b, end_b = b
    if start_a >= end_a or start_b >= end_b:
        return False
    return max(start_a, start_b) < min(end_a, end_b)


def _valid_span_for_linking(span: dict, whitelist: Sequence[str]) -> bool:
    """Validate that a span is eligible for linking."""
    tui = span.get("tui")
    if whitelist and tui not in whitelist:
        return False
    start, end = span.get("start"), span.get("end")
    if start is None or end is None or start >= end:
        return False
    text = span.get("text", "")
    return bool(text.strip())


def link_umls_spans(spans: Iterable[dict], whitelist: Sequence[str]) -> List[dict]:
    """Filter and deduplicate UMLS spans."""
    whitelist = tuple(whitelist)
    filtered: List[dict] = []

    for candidate in spans:
        if not _valid_span_for_linking(candidate, whitelist):
            continue
        start, end = candidate["start"], candidate["end"]
        if any(_overlap((start, end), (span["start"], span["end"])) for span in filtered):
            continue
        filtered.append(candidate)

    return filtered
