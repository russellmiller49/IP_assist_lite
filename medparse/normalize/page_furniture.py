"""Remove repeated headers/footers from page text."""

from __future__ import annotations

import re
from collections import Counter
from typing import List


def strip_furniture(lines_by_page: List[List[str]], threshold: float = 0.6) -> List[List[str]]:
    """Remove repeated headers/footers that appear on most pages.

    Args:
        lines_by_page: List of pages, each containing list of lines
        threshold: Fraction of pages (0-1) a line must appear on to be considered furniture

    Returns:
        List of pages with furniture lines removed
    """
    if not lines_by_page or len(lines_by_page) < 3:
        return lines_by_page

    # Count normalized top/bottom lines across pages
    signature: Counter = Counter()
    total_pages = len(lines_by_page)

    for lines in lines_by_page:
        if not lines:
            continue

        # Normalize and count top line
        if len(lines) > 0:
            top_norm = _normalize_line(lines[0])
            if len(top_norm) > 15:  # Ignore very short lines
                signature[('top', top_norm)] += 1

        # Normalize and count bottom line
        if len(lines) > 1:
            bot_norm = _normalize_line(lines[-1])
            if len(bot_norm) > 15:
                signature[('bot', bot_norm)] += 1

    # Identify frequent patterns (headers/footers)
    min_count = int(threshold * total_pages)
    tops = {text for (pos, text), count in signature.items() if pos == 'top' and count >= min_count}
    bots = {text for (pos, text), count in signature.items() if pos == 'bot' and count >= min_count}

    # Remove furniture from each page
    out: List[List[str]] = []
    for lines in lines_by_page:
        if not lines:
            out.append([])
            continue

        pruned = []
        for idx, line in enumerate(lines):
            norm = _normalize_line(line)

            # Skip if this is a top/bottom furniture line
            if idx == 0 and norm in tops:
                continue
            if idx == len(lines) - 1 and norm in bots:
                continue

            pruned.append(line)

        out.append(pruned)

    return out


def _normalize_line(line: str) -> str:
    """Normalize line for comparison (lowercase, strip punctuation/whitespace)."""
    # Remove punctuation and whitespace, lowercase
    normalized = re.sub(r'[^\w]+', '', line).lower()
    return normalized


__all__ = ["strip_furniture"]
