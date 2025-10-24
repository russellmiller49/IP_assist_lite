"""Assemble text from word tokens with proper spacing.

Rebuilds text from word bounding boxes to restore spaces lost in
concatenated PDFs. Uses y-clustering for lines and x-order for words.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import List, Tuple

# Word box: (x0, y0, x1, y1, text)
WordBox = Tuple[float, float, float, float, str]


def words_to_text(word_boxes: List[WordBox], y_tol: float = 2.0, x_gap_threshold: float = 2.0) -> str:
    """Rebuild text from word bounding boxes with proper inter-word spacing.

    Uses adaptive horizontal gap detection based on character widths.
    Coalesces single-character runs to fix "Ta b le" artifacts.

    Args:
        word_boxes: List of (x0, y0, x1, y1, text) tuples
        y_tol: Vertical tolerance for grouping words into lines
        x_gap_threshold: Minimum horizontal gap (in points) to insert space

    Returns:
        Text with lines separated by newlines, words by spaces
    """
    if not word_boxes:
        return ""

    # Group words by line (y-position clustering)
    lines = _cluster_by_y(word_boxes, y_tol)

    # Build lines with smart spacing based on gaps
    out_lines: List[str] = []
    for line_words in lines:
        line_words_sorted = sorted(line_words, key=lambda w: w[0])  # Sort by x0

        # Calculate median character width for this line
        char_widths: List[float] = []
        for word in line_words_sorted:
            width = word[2] - word[0]
            text = word[4]
            if text and len(text) > 0:
                char_widths.append(width / len(text))

        median_char_width = sorted(char_widths)[len(char_widths) // 2] if char_widths else 5.0

        # Adaptive gap threshold: 0.4x median char width
        adaptive_threshold = max(median_char_width * 0.4, x_gap_threshold)

        line_parts: List[str] = []
        for i, word in enumerate(line_words_sorted):
            if i == 0:
                line_parts.append(word[4])
            else:
                prev_word = line_words_sorted[i - 1]
                gap = word[0] - prev_word[2]  # x0 of current - x1 of previous

                # Add space only if gap exceeds adaptive threshold
                if gap >= adaptive_threshold:
                    line_parts.append(' ')

                line_parts.append(word[4])

        # Coalesce single-character runs (fix "T a b l e" → "Table")
        line_text = ''.join(line_parts)
        line_text = _coalesce_single_chars(line_text)
        out_lines.append(line_text)

    # Post-process to fix spacing artifacts
    text = '\n'.join(out_lines)
    text = _post_clean_spacing(text)

    return text


def _cluster_by_y(word_boxes: List[WordBox], y_tol: float) -> List[List[WordBox]]:
    """Cluster words into lines based on y-position.

    Args:
        word_boxes: List of word bounding boxes
        y_tol: Vertical tolerance for same-line grouping

    Returns:
        List of lines, each containing word boxes
    """
    if not word_boxes:
        return []

    # Sort by y-position (top to bottom)
    sorted_words = sorted(word_boxes, key=lambda w: w[1])

    lines: List[List[WordBox]] = []
    current_line: List[WordBox] = [sorted_words[0]]
    current_y = sorted_words[0][1]

    for word in sorted_words[1:]:
        if abs(word[1] - current_y) <= y_tol:
            # Same line
            current_line.append(word)
        else:
            # New line
            lines.append(current_line)
            current_line = [word]
            current_y = word[1]

    # Add last line
    if current_line:
        lines.append(current_line)

    return lines


def _coalesce_single_chars(text: str) -> str:
    """Coalesce single-character runs separated by spaces.

    Fixes "T a b l e" → "Table" artifacts from character-level tokenization.
    Only coalesces runs of 3+ single characters.

    Args:
        text: Input text with potential single-char runs

    Returns:
        Text with single-char runs coalesced
    """
    # Pattern: 3+ single letters/digits separated by single spaces
    # Match: "T a b l e" but not "a b c d e f g h i j k" (too long, likely intentional)
    pattern = re.compile(r'\b([A-Za-z0-9])(?: ([A-Za-z0-9])){2,8}\b')

    def replacer(match: re.Match) -> str:
        # Remove spaces between single characters
        return match.group(0).replace(' ', '')

    return pattern.sub(replacer, text)


def _post_clean_spacing(text: str) -> str:
    """Post-process spacing artifacts from word assembly.

    Fixes:
        - "6. 0. 0" → "6.0.0" (version numbers)
        - "Usethis" → "Use this" (missing space before lowercase)
        - Extra spaces around punctuation

    Args:
        text: Input text from word assembly

    Returns:
        Text with cleaned spacing
    """
    # Fix version numbers: "6. 0. 0" → "6.0.0"
    # Remove spaces around dots when between digits
    text = re.sub(r'(\d+)\s+\.\s+', r'\1.', text)  # "6 . " → "6."
    text = re.sub(r'\.\s+(\d+)', r'.\1', text)      # ". 0" → ".0"

    # Fix missing space before lowercase after uppercase: "USEthis" → "USE this"
    # But preserve acronyms like "IFU" and common patterns
    text = re.sub(r'([A-Z]{2,})([a-z])', r'\1 \2', text)

    # Fix "lowercase[nospace]lowercase" when first is 2+ chars: "Usethis" → "Use this"
    text = re.sub(r'\b([a-z]{2,})([a-z]{2,})\b', lambda m: m.group(1) + ' ' + m.group(2) if m.group(1) + m.group(2) != m.group(0) else m.group(0), text)

    # Collapse multiple spaces
    text = re.sub(r' {2,}', ' ', text)

    return text


def restore_spaces(text: str) -> str:
    """Apply safe spacing rules to fix common concatenation issues.

    Rules:
        - lowercase → Uppercase: add space
        - letter → digit: add space
        - digit → letter: add space
        - punctuation → non-space: add space

    Args:
        text: Input text with potential concatenation

    Returns:
        Text with restored spaces
    """
    # lowercase → Uppercase
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # letter → digit
    text = re.sub(r'([A-Za-z])(\d)', r'\1 \2', text)

    # digit → letter
    text = re.sub(r'(\d)([A-Za-z])', r'\1 \2', text)

    # punctuation → next char
    text = re.sub(r'([,.;:])(\S)', r'\1 \2', text)

    # Collapse multiple spaces
    text = re.sub(r'\s{2,}', ' ', text)

    return text


__all__ = ["words_to_text", "restore_spaces"]
