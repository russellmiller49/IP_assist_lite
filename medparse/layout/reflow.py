"""Primitive layout reflow utilities for Docling output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Block:
    text: str
    bbox: Tuple[float, float, float, float]
    page: int


def _detect_column_split(blocks: List[Block], min_gap_ratio: float = 0.18, min_per_col: int = 2) -> float | None:
    """Return x-threshold that separates columns when a strong gutter is present."""

    if len(blocks) < (min_per_col * 2):
        return None

    centers = []
    for blk in blocks:
        x0, _, x1, _ = blk.bbox
        centers.append(((x0 + x1) / 2.0, blk))
    centers.sort(key=lambda pair: pair[0])

    min_x = min(x for x, _ in centers)
    max_x = max(x for x, _ in centers)
    width = max(max_x - min_x, 1.0)

    gaps: List[Tuple[float, int]] = []
    for idx in range(len(centers) - 1):
        gap = centers[idx + 1][0] - centers[idx][0]
        gaps.append((gap, idx))
    if not gaps:
        return None

    gaps.sort(key=lambda item: item[0], reverse=True)
    gap_value, gap_idx = gaps[0]
    if (gap_value / width) < min_gap_ratio:
        return None

    left_count = gap_idx + 1
    right_count = len(centers) - left_count
    if left_count < min_per_col or right_count < min_per_col:
        return None

    return (centers[gap_idx][0] + centers[gap_idx + 1][0]) / 2.0


def _cluster_columns(blocks: List[Block], max_columns: int = 3) -> List[List[Block]]:
    """Heuristically partition blocks into 1-3 reading columns."""

    if not blocks:
        return []
    xs = [(blk, (blk.bbox[0] + blk.bbox[2]) / 2.0) for blk in blocks]
    xs.sort(key=lambda item: item[1])

    def split_by_gaps(items: List[Tuple[Block, float]], k: int) -> List[List[Block]]:
        if k <= 1 or len(items) <= 1:
            return [[blk for blk, _ in items]]
        diffs = [(idx, items[idx + 1][1] - items[idx][1]) for idx in range(len(items) - 1)]
        diffs.sort(key=lambda item: item[1], reverse=True)
        cuts = sorted(idx for idx, _ in diffs[: k - 1])
        grouped: List[List[Block]] = []
        start = 0
        for cut in cuts:
            grouped.append([blk for blk, _ in items[start : cut + 1]])
            start = cut + 1
        grouped.append([blk for blk, _ in items[start:]])
        return grouped

    for k in (2, 3):
        groups = split_by_gaps(xs, k)
        groups = [[blk for blk in group if blk.text.strip()] for group in groups if group]
        total = sum(len(group) for group in groups)
        if total >= max(1, int(0.8 * len(blocks))):
            for group in groups:
                group.sort(key=lambda blk: (blk.page, blk.bbox[1], blk.bbox[0]))
            return groups

    ordered = [blk for blk, _ in xs]
    ordered.sort(key=lambda blk: (blk.page, blk.bbox[1], blk.bbox[0]))
    return [ordered]


def drop_headers_footers(
    blocks: List[Block],
    page_height: float,
    *,
    header_h: float = 48.0,
    footer_h: float = 48.0,
) -> List[Block]:
    """Remove blocks that live in the header/footer bands."""

    stripped: List[Block] = []
    for block in blocks:
        y0, y1 = block.bbox[1], block.bbox[3]
        if y1 <= header_h:
            continue
        if (page_height - y0) <= footer_h:
            continue
        stripped.append(block)
    return stripped


def reflow_page(blocks: List[Block], page_height: float) -> List[Block]:
    """Return blocks ordered by reading sequence for the page."""

    filtered = drop_headers_footers(blocks, page_height)
    if not filtered:
        return filtered

    split_x = _detect_column_split(filtered)
    if split_x is not None:
        left: List[Block] = []
        right: List[Block] = []
        for blk in filtered:
            x0, _, x1, _ = blk.bbox
            center = (x0 + x1) / 2.0
            (left if center <= split_x else right).append(blk)
        left.sort(key=lambda blk: (blk.page, blk.bbox[1], blk.bbox[0]))
        right.sort(key=lambda blk: (blk.page, blk.bbox[1], blk.bbox[0]))
        return left + right

    column_groups = _cluster_columns(filtered)
    if not column_groups:
        return filtered

    ordered: List[Block] = []
    for group in column_groups:
        ordered.extend(group)
    return ordered


__all__ = ["Block", "drop_headers_footers", "reflow_page"]
