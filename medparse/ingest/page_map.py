"""Helpers for mapping text spans back to PDF pages."""

from __future__ import annotations

from bisect import bisect_right
from typing import Callable, List, Optional, Sequence, Tuple

from medparse.ingest.pdf_reader import PageContent, TextBlock


def build_full_text_with_spans(
    pages: Sequence[PageContent],
) -> Tuple[str, Callable[[int], Tuple[int, float] | None]]:
    """Concatenate page blocks while keeping page resolution capability."""
    pieces: List[str] = []
    spans: List[Tuple[int, int, int]] = []  # (start, end, page)
    position = 0

    for page in pages:
        page_contributed = False
        for block in page.blocks:
            text = block.text.strip()
            if not text:
                continue

            if pieces:
                pieces.append("\n")
                position += 1

            start = position
            pieces.append(text)
            position += len(text)
            spans.append((start, position, page.number))
            page_contributed = True

        if not page_contributed:
            fallback_lines = [line.strip() for line in page.lines if line.strip()]
            if fallback_lines:
                text = " ".join(fallback_lines)
                if pieces:
                    pieces.append("\n")
                    position += 1
                start = position
                pieces.append(text)
                position += len(text)
                spans.append((start, position, page.number))

    full_text = "".join(pieces)
    starts = [start for start, _, _ in spans]

    def resolve_page(offset: int) -> Tuple[int, float] | None:
        if offset < 0 or offset >= len(full_text):
            return None
        idx = bisect_right(starts, offset) - 1
        candidates: List[Tuple[int, int, int]] = []
        if 0 <= idx < len(spans):
            candidates.append(spans[idx])
        if 0 <= idx + 1 < len(spans):
            candidates.append(spans[idx + 1])

        for start, end, page in candidates:
            if start <= offset < end:
                return page, 1.0

        best_page: Optional[int] = None
        best_distance = 201
        for start, end, page in candidates:
            if start <= offset:
                distance = offset - min(end - 1, offset)
            else:
                distance = start - offset
            if distance < best_distance:
                best_distance = distance
                best_page = page

        if best_page is not None and best_distance <= 200:
            return best_page, 0.6
        return None

    return full_text, resolve_page
