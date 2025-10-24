"""Article section extraction with column-aware reading and TOC exclusion."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from medparse.ingest.models import PageData
from medparse.normalize.text_cleanup import (
    clean_paragraph,
    collapse_runs,
    normalize_ligatures,
)


# Standard article section anchors
SECTION_ANCHORS = {
    'abstract': ['abstract', 'summary'],
    'background': ['background', 'introduction', 'rationale'],
    'methods': ['methods', 'materials and methods', 'patients and methods', 'study design'],
    'results': ['results', 'findings'],
    'discussion': ['discussion', 'interpretation'],
    'conclusion': ['conclusion', 'conclusions', 'summary'],
    'limitations': ['limitations', 'study limitations'],
    'funding': ['funding', 'financial support', 'grant support'],
    'conflicts': ['conflict of interest', 'conflicts of interest', 'disclosures'],
    'ethics': ['ethics', 'institutional review board', 'irb approval', 'ethics statement'],
}


def is_toc_page(text: str) -> bool:
    """Detect if page is a Table of Contents page.

    Args:
        text: Page text

    Returns:
        True if page appears to be TOC
    """
    # Look for TOC indicators
    toc_markers = [
        r'table\s+of\s+contents',
        r'contents\s*\n',
        r'^\d+\.?\s+[A-Z][^.]{10,}\s+\.\s+\d+$',  # Numbered entries with page numbers
        r'chapter\s+\d+\s+\.+\s+\d+',
    ]

    text_lower = text.lower()
    for marker in toc_markers:
        if re.search(marker, text_lower, re.MULTILINE):
            return True

    # Check for high density of dotted lines (TOC formatting)
    dotted_lines = len(re.findall(r'\.{3,}', text))
    total_lines = len(text.split('\n'))
    if total_lines > 0 and dotted_lines / total_lines > 0.3:
        return True

    return False


def detect_column_layout(pages: List[PageData]) -> int:
    """Detect 1-column vs 2-column layout using spatial heuristics.

    Args:
        pages: Pages to analyze

    Returns:
        1 or 2 (number of columns)
    """
    if not pages:
        return 1

    # Check first content page (skip cover)
    page = pages[1] if len(pages) > 1 else pages[0]

    # Check if we have word-level bounding boxes
    # For now, use heuristic: look for mid-page gap in text
    # If layout info is unavailable, assume single column
    if not hasattr(page, 'word_boxes') or not page.word_boxes:
        # Fallback: analyze line lengths
        return detect_column_from_line_lengths(page)

    # Analyze x-coordinates of words
    try:
        x_coords = [box[0] for box in page.word_boxes if len(box) > 0]
        if not x_coords:
            return 1

        page_width = max(box[2] if len(box) > 2 else box[0] for box in page.word_boxes)

        # Look for gutter (empty vertical strip in middle)
        mid_left = page_width * 0.4
        mid_right = page_width * 0.6
        words_in_middle = sum(1 for x in x_coords if mid_left < x < mid_right)

        # If <10% of words in middle third, likely 2-column
        if len(x_coords) > 0 and words_in_middle / len(x_coords) < 0.1:
            return 2

    except (AttributeError, TypeError, IndexError):
        pass

    return 1


def detect_column_from_line_lengths(page: PageData) -> int:
    """Detect columns from line length variation.

    Args:
        page: Page to analyze

    Returns:
        1 or 2 (number of columns)
    """
    if not page.lines:
        return 1

    # In 2-column layout, lines are typically shorter and more uniform
    line_lengths = [len(line.strip()) for line in page.lines if line.strip()]
    if not line_lengths:
        return 1

    avg_len = sum(line_lengths) / len(line_lengths)

    # 2-column typically has avg line length < 60 chars
    # 1-column typically > 80 chars
    if avg_len < 70:
        return 2

    return 1


def reflow_two_column(pages: List[PageData]) -> List[PageData]:
    """Reflow text for 2-column layout (left→right per page).

    Args:
        pages: Pages to reflow

    Returns:
        Pages with reflowed text
    """
    reflowed_pages = []

    for page in pages:
        # If we don't have word boxes, skip reflow
        if not hasattr(page, 'word_boxes') or not page.word_boxes:
            reflowed_pages.append(page)
            continue

        try:
            # Determine page midpoint
            all_x = [box[0] for box in page.word_boxes if len(box) > 0]
            if not all_x:
                reflowed_pages.append(page)
                continue

            page_width = max(box[2] if len(box) > 2 else box[0] + 50 for box in page.word_boxes)
            midpoint = page_width / 2

            # Split into left and right columns
            left_words = [w for w in page.word_boxes if w[0] < midpoint]
            right_words = [w for w in page.word_boxes if w[0] >= midpoint]

            # Sort by vertical position (y-coordinate)
            left_words.sort(key=lambda w: w[1] if len(w) > 1 else 0)
            right_words.sort(key=lambda w: w[1] if len(w) > 1 else 0)

            # Extract text from left, then right
            left_text = ' '.join(w[4] if len(w) > 4 else str(w) for w in left_words)
            right_text = ' '.join(w[4] if len(w) > 4 else str(w) for w in right_words)

            # Update page text
            page.text = left_text + '\n' + right_text
            page.lines = page.text.split('\n')

        except (IndexError, TypeError, AttributeError):
            # Fallback: keep original
            pass

        reflowed_pages.append(page)

    return reflowed_pages


def slice_between(
    pages: List[PageData],
    start_anchors: List[str],
    stop_anchors: Optional[List[str]] = None,
    exclude_toc: bool = True
) -> str:
    """Extract text between start and stop anchors with TOC exclusion.

    Args:
        pages: Pages to search
        start_anchors: Heading patterns to start extraction
        stop_anchors: Heading patterns to end extraction (optional)
        exclude_toc: Skip TOC pages

    Returns:
        Extracted text
    """
    # Filter out TOC pages if requested
    if exclude_toc:
        pages = [p for p in pages if not is_toc_page('\n'.join(p.lines))]

    full_text = '\n'.join('\n'.join(p.lines) for p in pages)

    # Find start position
    start_pos = None
    for anchor in start_anchors:
        # Look for anchor as heading (start of line, followed by colon or newline)
        pattern = rf'(?:^|\n)({re.escape(anchor)})[:\s]*\n'
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            start_pos = match.end()
            break

    if start_pos is None:
        return ""

    # Find stop position
    stop_pos = len(full_text)
    if stop_anchors:
        for anchor in stop_anchors:
            pattern = rf'(?:^|\n)({re.escape(anchor)})[:\s]*\n'
            match = re.search(pattern, full_text[start_pos:], re.IGNORECASE)
            if match:
                stop_pos = start_pos + match.start()
                break

    # Extract slice
    text = full_text[start_pos:stop_pos]

    return text.strip()


def normalize_article_sections(pages: List[PageData]) -> Dict[str, str]:
    """Extract and normalize article sections with column awareness and TOC exclusion.

    Args:
        pages: Document pages

    Returns:
        Dictionary mapping section names to clean text
    """
    # Detect column layout
    column_mode = detect_column_layout(pages)

    # Reflow if 2-column
    if column_mode == 2:
        pages = reflow_two_column(pages)

    # Filter out TOC pages
    non_toc_pages = [p for p in pages if not is_toc_page('\n'.join(p.lines))]

    sections = {}

    # Extract each section
    for section_key, start_anchors in SECTION_ANCHORS.items():
        # Build stop anchors (all other section headings)
        all_anchors = [a for anchors in SECTION_ANCHORS.values() for a in anchors]
        stop_anchors = [a for a in all_anchors if a not in start_anchors]

        # Extract bounded section
        raw_text = slice_between(
            non_toc_pages,
            start_anchors=start_anchors,
            stop_anchors=stop_anchors,
            exclude_toc=True
        )

        if raw_text:
            # Post-process: normalize whitespace, fix hyphenation
            clean_text = dehyphenate(raw_text)
            clean_text = clean_paragraph(clean_text)
            sections[section_key] = clean_text

    return sections


def dehyphenate(text: str) -> str:
    """Fix end-of-line hyphenation (smart: only join if lowercase after hyphen).

    Args:
        text: Text with potential hyphenation artifacts

    Returns:
        Text with smart dehyphenation applied
    """
    # Pattern: word ending with hyphen, newline, then lowercase word
    # Only join if the next character is lowercase (not a new sentence)
    pattern = r'(\w)-\s*\n\s*([a-z])'
    text = re.sub(pattern, r'\1\2', text)

    return text


def find_first_occurrence_page(pages: List[PageData], anchors: List[str]) -> Optional[int]:
    """Find page number where any anchor first occurs.

    Args:
        pages: Pages to search
        anchors: Heading patterns to find

    Returns:
        Page number (0-indexed) or None
    """
    for i, page in enumerate(pages):
        page_text = '\n'.join(page.lines).lower()
        for anchor in anchors:
            if anchor.lower() in page_text:
                return i

    return None


__all__ = [
    "normalize_article_sections",
    "is_toc_page",
    "slice_between",
    "detect_column_layout",
    "reflow_two_column",
    "dehyphenate",
]
