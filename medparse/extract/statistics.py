"""Extract statistical statements (percentages) from text."""

from __future__ import annotations

import re
from typing import Iterable, List

STAT_RE = re.compile(r"(?P<value>\d{1,3}(?:\.\d+)?)%")
GRANT_RE = re.compile(r"\b(?:U0\d|R0\d|NCT\d+)\b", re.IGNORECASE)
CITATION_RE = re.compile(r"\(\s*\d{4};\s*\d+:\s*\d+(?:-\d+)?\s*\)")
REFERENCE_BLOCKERS = ("doi", "pmid", "vol.")


def _is_grant_or_identifier(text: str) -> bool:
    return bool(GRANT_RE.search(text))


def _is_pure_citation_tuple(text: str) -> bool:
    snippet = text.strip()
    return bool(CITATION_RE.fullmatch(snippet))


def _is_reference_context(text: str) -> bool:
    lowered = text.lower()
    return any(blocker in lowered for blocker in REFERENCE_BLOCKERS)


def extract_statistics(paragraphs: Iterable[str]) -> List[dict]:
    """Return statistical mentions within the provided paragraphs."""
    stats: List[dict] = []

    for paragraph in paragraphs:
        if not paragraph:
            continue
        for match in STAT_RE.finditer(paragraph):
            context = paragraph[max(0, match.start() - 40) : match.end() + 40]
            if (
                _is_grant_or_identifier(context)
                or _is_pure_citation_tuple(context.strip())
                or _is_reference_context(context)
            ):
                continue
            stats.append(
                {
                    "value": float(match.group("value")),
                    "context": re.sub(r"\s+", " ", context).strip(),
                }
            )

    return stats
