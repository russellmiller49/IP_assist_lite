"""Text-processing utilities."""

import re
from typing import Iterable, List


WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace and strip ends."""
    return WHITESPACE_RE.sub(" ", text).strip()


def collapse_whitespace(text: str) -> str:
    """Alias for ``normalize_whitespace`` to aid readability."""
    return normalize_whitespace(text)


def window(iterable: Iterable[str], size: int) -> List[str]:
    """Return a list of size-length windows from the iterable."""
    items = list(iterable)
    return [" ".join(items[i : i + size]) for i in range(0, len(items), size)]
