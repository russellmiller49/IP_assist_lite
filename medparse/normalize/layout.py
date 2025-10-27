"""Layout utilities shared across extractors.

Provides TOC detection, column reflow, and bounded text slicing that guards
against common layout regressions (two-column bleed, table of contents bleed,
etc.).  These helpers operate on ``PageData`` structures emitted by the ingest
layer and avoid mutating the original instances so callers can opt-in to the
reflowed copies only when needed.
"""

from __future__ import annotations

import re
from dataclasses import replace
from statistics import mean
from typing import Callable, Iterable, List, Optional, Sequence

from medparse.ingest.models import PageData, WordBox
from medparse.normalize.text_assemble import words_to_text

GuardFn = Callable[[PageData], bool]


def is_toc_page(page: PageData) -> bool:
    """Heuristic TOC detector based on keywords and layout patterns."""

    if not page.lines:
        return False

    joined = "\n".join(line for line in page.lines if line.strip())
    lowered = joined.lower()

    # Strong keyword indicators
    if "table of contents" in lowered or lowered.startswith("contents"):
        return True

    # TOCs frequently have many dotted leaders and terminal page numbers
    dotted_lines = sum(1 for line in page.lines if re.search(r"\.{4,}", line))
    numbered_trailing = sum(
        1 for line in page.lines if re.search(r"\s\d{1,4}\s*$", line)
    )
    headings_like = sum(
        1
        for line in page.lines
        if re.match(r"^\d+(?:\.\d+)*\s+[A-Z][^\n]{5,}", line.strip())
    )

    total_lines = max(len(page.lines), 1)

    dotted_ratio = dotted_lines / total_lines
    numbered_ratio = numbered_trailing / total_lines

    if dotted_ratio >= 0.15 and numbered_ratio >= 0.15:
        return True
    if headings_like >= 4 and numbered_ratio >= 0.2:
        return True

    # Short cover pages with only chapter numbers shouldn't be flagged
    return False


def detect_column_layout(page: PageData, gutter_band: tuple[float, float] = (0.42, 0.58)) -> int:
    """Return the number of text columns detected for ``page`` (1 or 2)."""

    boxes = page.word_boxes
    if not boxes:
        return 1

    x0_values = [box[0] for box in boxes]
    x1_values = [box[2] for box in boxes if len(box) > 2]
    if not x0_values or not x1_values:
        return 1

    min_x = min(x0_values)
    max_x = max(x1_values)
    width = max(max_x - min_x, 1.0)

    gutter_left = min_x + width * gutter_band[0]
    gutter_right = min_x + width * gutter_band[1]

    middle_tokens = sum(
        1 for box in boxes if gutter_left <= box[0] <= gutter_right
    )
    total_tokens = len(boxes)

    if total_tokens == 0:
        return 1

    middle_ratio = middle_tokens / total_tokens
    left_tokens = sum(1 for box in boxes if box[0] < gutter_left)
    right_tokens = sum(1 for box in boxes if box[0] > gutter_right)

    # Require healthy populations on both sides and a sparse gutter
    if (
        middle_ratio <= 0.12
        and left_tokens >= total_tokens * 0.25
        and right_tokens >= total_tokens * 0.25
    ):
        return 2

    return 1


def reflow_columns(page: PageData, *, max_columns: int = 2) -> PageData:
    """Return a copy of ``page`` with text reflowed left→right for multi-column."""

    if max_columns < 2:
        return page

    columns = detect_column_layout(page)
    if columns < 2 or not page.word_boxes:
        return page

    split_x = _determine_split_threshold(page.word_boxes)
    if split_x is None:
        return page

    left_boxes = [box for box in page.word_boxes if box[0] <= split_x]
    right_boxes = [box for box in page.word_boxes if box[0] > split_x]

    if not left_boxes or not right_boxes:
        return page

    left_text = words_to_text(left_boxes)
    right_text = words_to_text(right_boxes)

    column_texts = [column.strip() for column in (left_text, right_text) if column.strip()]
    if not column_texts:
        return page

    combined_text = "\n".join(column_texts)
    combined_lines = [
        line for block in column_texts for line in block.splitlines() if line.strip()
    ]

    return replace(page, text=combined_text, lines=combined_lines)


def reflow_document(pages: Sequence[PageData], *, max_columns: int = 2) -> List[PageData]:
    """Return reflowed copies of ``pages``."""

    return [reflow_columns(page, max_columns=max_columns) for page in pages]


def slice_between(
    pages: Sequence[PageData],
    *,
    start_anchors: Iterable[str],
    stop_anchors: Optional[Iterable[str]] = None,
    guard_fn: GuardFn | None = is_toc_page,
) -> str:
    """Extract text bounded by anchors, guarding against TOC bleed."""

    filtered_pages = [
        page for page in pages if not guard_fn or not guard_fn(page)
    ]
    if not filtered_pages:
        return ""

    joined = "\n".join("\n".join(page.lines) for page in filtered_pages)
    start = _find_anchor(joined, start_anchors)
    if start is None:
        return ""

    end = _find_anchor(joined[start:], stop_anchors)
    slice_text = joined[start : start + end if end is not None else None]
    return slice_text.strip()


def _find_anchor(text: str, anchors: Optional[Iterable[str]]) -> Optional[int]:
    if not anchors:
        return None

    for anchor in anchors:
        # Headings typically start at line boundaries; allow colon or new line
        pattern = rf"(?:^|\n)\s*{re.escape(anchor)}[:\s]*\n"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.end()

    return None


def _determine_split_threshold(boxes: Sequence[WordBox]) -> Optional[float]:
    """Return an x-threshold that separates left/right columns."""

    if not boxes:
        return None

    midpoints = sorted(((box[0] + box[2]) / 2.0) for box in boxes if len(box) >= 3)
    if len(midpoints) < 4:
        return None

    gaps = [
        (b - a, a, b)
        for a, b in zip(midpoints, midpoints[1:])
        if a != b
    ]
    if not gaps:
        return None

    # Prefer gaps located near the middle 40–60% of the page width
    avg_mid = mean(midpoints)
    width = max(midpoints) - min(midpoints)
    left_bound = min(midpoints) + width * 0.25
    right_bound = min(midpoints) + width * 0.75

    candidate_gaps = [
        gap for gap in gaps if left_bound <= gap[1] <= right_bound
    ] or gaps

    best_gap = max(candidate_gaps, key=lambda item: item[0])
    _, a, b = best_gap
    return (a + b) / 2.0


__all__ = [
    "detect_column_layout",
    "is_toc_page",
    "reflow_columns",
    "reflow_document",
    "slice_between",
]

