"""Multi-column layout detection and reading order correction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import List, Optional, Sequence, Tuple

from medparse.ingest.models import PageData, TextBlock


@dataclass(slots=True)
class Column:
    """Represents a detected column with its boundaries."""

    index: int  # Column number (0, 1, 2...)
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    blocks: List[TextBlock]

    @property
    def x_center(self) -> float:
        return (self.x_min + self.x_max) / 2

    @property
    def width(self) -> float:
        return self.x_max - self.x_min


@dataclass(slots=True)
class LayoutAnalysis:
    """Analysis results for page layout."""

    is_multi_column: bool
    num_columns: int
    columns: List[Column]
    reading_order_blocks: List[TextBlock]
    confidence: float


def detect_columns(page: PageData, *, min_column_width: float = 200.0) -> LayoutAnalysis:
    """Detect multi-column layout and correct reading order.

    Args:
        page: Page data with text blocks
        min_column_width: Minimum column width in points (default 200pt ~= 2.8 inches)

    Returns:
        Layout analysis with corrected reading order
    """
    if not page.blocks:
        return LayoutAnalysis(
            is_multi_column=False,
            num_columns=1,
            columns=[],
            reading_order_blocks=[],
            confidence=0.0,
        )

    # Filter blocks with position information
    positioned_blocks = [
        b for b in page.blocks
        if b.bbox and len(b.bbox) == 4 and b.text.strip()
    ]

    if not positioned_blocks:
        return LayoutAnalysis(
            is_multi_column=False,
            num_columns=1,
            columns=[],
            reading_order_blocks=list(page.blocks),
            confidence=1.0,
        )

    # Extract x-coordinates
    x_coords = [(b.bbox[0], b.bbox[2]) for b in positioned_blocks]
    x_lefts = [x[0] for x in x_coords]
    x_rights = [x[1] for x in x_coords]

    # Detect column boundaries using clustering
    columns = _cluster_columns(positioned_blocks, min_column_width)

    if len(columns) <= 1:
        # Single column layout - use top-to-bottom order
        sorted_blocks = sorted(
            positioned_blocks,
            key=lambda b: (b.bbox[1], b.bbox[0])  # Sort by y, then x
        )
        return LayoutAnalysis(
            is_multi_column=False,
            num_columns=1,
            columns=columns,
            reading_order_blocks=sorted_blocks,
            confidence=1.0,
        )

    # Multi-column layout detected
    # Sort columns left to right
    columns.sort(key=lambda c: c.x_center)

    # Re-index columns
    for idx, col in enumerate(columns):
        col.index = idx

    # Build reading order: read each column top-to-bottom, left-to-right
    reading_order_blocks = []
    for column in columns:
        # Sort blocks within column by vertical position
        sorted_col_blocks = sorted(
            column.blocks,
            key=lambda b: (b.bbox[1], b.bbox[0])
        )
        reading_order_blocks.extend(sorted_col_blocks)

    # Calculate confidence based on column separation
    confidence = _calculate_column_confidence(columns)

    return LayoutAnalysis(
        is_multi_column=True,
        num_columns=len(columns),
        columns=columns,
        reading_order_blocks=reading_order_blocks,
        confidence=confidence,
    )


def _cluster_columns(blocks: List[TextBlock], min_width: float) -> List[Column]:
    """Cluster blocks into columns based on x-coordinates."""
    if not blocks:
        return []

    # Extract x-centers
    block_centers = []
    for block in blocks:
        if block.bbox and len(block.bbox) == 4:
            x_center = (block.bbox[0] + block.bbox[2]) / 2
            block_centers.append((x_center, block))

    if not block_centers:
        return []

    # Sort by x-center
    block_centers.sort(key=lambda x: x[0])

    # Find gaps that indicate column boundaries
    gaps = []
    for i in range(len(block_centers) - 1):
        curr_x = block_centers[i][0]
        next_x = block_centers[i + 1][0]
        gap = next_x - curr_x
        if gap > 20:  # Significant gap (> 20 points)
            gaps.append((i, gap))

    # If no significant gaps, single column
    if not gaps:
        y_coords = [b.bbox[1] for b in blocks if b.bbox]
        all_column = Column(
            index=0,
            x_min=min(b.bbox[0] for b in blocks if b.bbox),
            x_max=max(b.bbox[2] for b in blocks if b.bbox),
            y_min=min(y_coords) if y_coords else 0,
            y_max=max(y_coords) if y_coords else 0,
            blocks=blocks,
        )
        return [all_column]

    # Find the largest gap as column separator
    largest_gap = max(gaps, key=lambda x: x[1])
    gap_threshold = largest_gap[1] * 0.5  # Use 50% of largest gap

    # Split into columns at gaps
    column_splits = [i for i, gap in gaps if gap >= gap_threshold]

    columns: List[Column] = []
    start_idx = 0

    for split_idx in column_splits:
        col_blocks = [bc[1] for bc in block_centers[start_idx:split_idx + 1]]
        if col_blocks:
            bbox_list = [b.bbox for b in col_blocks if b.bbox]
            if bbox_list:
                y_coords = [bbox[1] for bbox in bbox_list]
                column = Column(
                    index=len(columns),
                    x_min=min(bbox[0] for bbox in bbox_list),
                    x_max=max(bbox[2] for bbox in bbox_list),
                    y_min=min(y_coords),
                    y_max=max(y_coords),
                    blocks=col_blocks,
                )
                columns.append(column)
        start_idx = split_idx + 1

    # Last column
    col_blocks = [bc[1] for bc in block_centers[start_idx:]]
    if col_blocks:
        bbox_list = [b.bbox for b in col_blocks if b.bbox]
        if bbox_list:
            y_coords = [bbox[1] for bbox in bbox_list]
            column = Column(
                index=len(columns),
                x_min=min(bbox[0] for bbox in bbox_list),
                x_max=max(bbox[2] for bbox in bbox_list),
                y_min=min(y_coords),
                y_max=max(y_coords),
                blocks=col_blocks,
            )
            columns.append(column)

    # Filter out columns that are too narrow (likely sidebars/page numbers)
    columns = [col for col in columns if col.width >= min_width or len(col.blocks) >= 10]

    return columns


def _calculate_column_confidence(columns: List[Column]) -> float:
    """Calculate confidence that columns are correctly detected.

    Based on:
    - Column width consistency
    - Gap size between columns
    - Number of blocks per column
    """
    if len(columns) <= 1:
        return 1.0

    widths = [col.width for col in columns]
    avg_width = sum(widths) / len(widths)

    # Check width consistency (coefficient of variation)
    if avg_width > 0:
        width_variance = sum((w - avg_width) ** 2 for w in widths) / len(widths)
        width_cv = (width_variance ** 0.5) / avg_width
    else:
        width_cv = 1.0

    # Lower CV = higher confidence
    width_confidence = max(0.0, 1.0 - width_cv)

    # Check gaps between columns
    gaps = []
    for i in range(len(columns) - 1):
        gap = columns[i + 1].x_min - columns[i].x_max
        gaps.append(gap)

    if gaps:
        avg_gap = sum(gaps) / len(gaps)
        # Larger gaps = higher confidence
        gap_confidence = min(1.0, avg_gap / 50.0)  # 50pt gap = 100% confident
    else:
        gap_confidence = 0.5

    # Check block distribution
    block_counts = [len(col.blocks) for col in columns]
    total_blocks = sum(block_counts)
    if total_blocks > 0:
        # Ideally blocks evenly distributed
        expected_per_col = total_blocks / len(columns)
        distribution_variance = sum(
            (count - expected_per_col) ** 2 for count in block_counts
        ) / len(block_counts)
        distribution_cv = (distribution_variance ** 0.5) / expected_per_col if expected_per_col > 0 else 1.0
        distribution_confidence = max(0.0, 1.0 - distribution_cv * 0.5)
    else:
        distribution_confidence = 0.0

    # Weighted average
    confidence = (
        0.4 * width_confidence +
        0.4 * gap_confidence +
        0.2 * distribution_confidence
    )

    return confidence


def rebuild_lines_with_reading_order(
    page: PageData,
    layout: LayoutAnalysis,
) -> List[str]:
    """Rebuild page lines using correct reading order from layout analysis.

    Args:
        page: Original page data
        layout: Layout analysis with corrected reading order

    Returns:
        Lines in correct reading order
    """
    if not layout.is_multi_column or not layout.reading_order_blocks:
        return list(page.lines or [])

    # Rebuild lines from blocks in correct order
    lines = []
    for block in layout.reading_order_blocks:
        if block.text:
            # Split block text into lines if it contains newlines
            block_lines = block.text.splitlines()
            lines.extend(line for line in block_lines if line.strip())

    return lines


__all__ = [
    "Column",
    "LayoutAnalysis",
    "detect_columns",
    "rebuild_lines_with_reading_order",
]
