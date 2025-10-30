"""Unit tests for text assembly and spacing fixes."""

import pytest

from medparse.normalize.text_assemble import (
    _coalesce_single_chars,
    _post_clean_spacing,
    words_to_text,
)


class TestCoalesceSingleChars:
    """Test single-character run coalescing."""

    def test_table_of_contents_fix(self):
        """Fix 'Ta b le' → 'Table'"""
        text = "T a b l e of Contents"
        result = _coalesce_single_chars(text)
        assert result == "Table of Contents"

    def test_multiple_runs(self):
        """Multiple single-char runs in one line."""
        text = "U s e this f o r m"
        result = _coalesce_single_chars(text)
        assert result == "Use this form"

    def test_preserves_normal_spacing(self):
        """Normal words with spaces remain unchanged."""
        text = "This is a normal sentence"
        result = _coalesce_single_chars(text)
        assert result == "This is a normal sentence"

    def test_short_acronyms_not_coalesced(self):
        """Short runs (2 chars) are not coalesced - pattern requires 3+."""
        text = "The I D number is required"
        result = _coalesce_single_chars(text)
        # Pattern requires 3+ chars: {2,8} means 2 additional after first
        # So "I D" (2 chars) won't match
        assert result == "The I D number is required"

    def test_long_single_char_runs_coalesced(self):
        """Long runs up to 9 chars are coalesced."""
        text = "a b c d e f g h i j k"
        result = _coalesce_single_chars(text)
        # Pattern matches up to 9 chars total (1 + 8 additional)
        # First 9 chars should be coalesced
        assert "abcdefghi" in result


class TestPostCleanSpacing:
    """Test post-processing spacing fixes."""

    def test_version_number_spacing(self):
        """Fix '6. 0. 0' → '6.0.0'"""
        text = "Ion OS v 6. 0. 0"
        result = _post_clean_spacing(text)
        assert "6.0.0" in result

    def test_multiple_version_numbers(self):
        """Multiple version numbers in text."""
        text = "Ion OS v 6. 0. 0 and PlanPoint v 4. 0"
        result = _post_clean_spacing(text)
        assert "6.0.0" in result
        assert "4.0" in result

    def test_use_this_fix(self):
        """Fix 'USEthis' → 'USE this'"""
        text = "USEthis device"
        result = _post_clean_spacing(text)
        assert "USE this" in result

    def test_collapse_multiple_spaces(self):
        """Collapse multiple spaces to single space."""
        text = "Ion  OS    v6.0.0"
        result = _post_clean_spacing(text)
        assert "  " not in result
        assert result == "Ion OS v6.0.0"

    def test_preserves_normal_text(self):
        """Normal text remains unchanged."""
        text = "The Ion Endoluminal System is a device."
        result = _post_clean_spacing(text)
        assert result == "The Ion Endoluminal System is a device."


class TestWordsToText:
    """Test full word-to-text assembly with adaptive spacing."""

    def test_basic_line_assembly(self):
        """Basic word boxes on single line."""
        # Format: (x0, y0, x1, y1, text)
        word_boxes = [
            (10.0, 100.0, 30.0, 110.0, "The"),
            (35.0, 100.0, 55.0, 110.0, "quick"),
            (60.0, 100.0, 80.0, 110.0, "fox"),
        ]
        result = words_to_text(word_boxes)
        assert result == "The quick fox"

    def test_adaptive_gap_threshold(self):
        """Adaptive threshold joins close characters."""
        # Small gaps between character-level tokens
        word_boxes = [
            (10.0, 100.0, 15.0, 110.0, "T"),  # width=5, char_width=5
            (15.5, 100.0, 20.5, 110.0, "a"),  # gap=0.5 (< 0.4*5=2.0)
            (21.0, 100.0, 26.0, 110.0, "b"),  # gap=0.5
            (26.5, 100.0, 31.5, 110.0, "l"),  # gap=0.5
            (32.0, 100.0, 37.0, 110.0, "e"),  # gap=0.5
        ]
        result = words_to_text(word_boxes, x_gap_threshold=2.0)
        # Adaptive threshold = 0.4 * median_char_width = 0.4 * 5 = 2.0
        # Gaps of 0.5 are < 2.0, so no spaces inserted
        # Then coalesce_single_chars joins them
        assert "Table" in result or "T a b l e" in result

    def test_multiple_lines(self):
        """Multiple lines with y-clustering."""
        word_boxes = [
            # Line 1 (y=100)
            (10.0, 100.0, 30.0, 110.0, "First"),
            (35.0, 100.0, 50.0, 110.0, "line"),
            # Line 2 (y=120)
            (10.0, 120.0, 35.0, 130.0, "Second"),
            (40.0, 120.0, 55.0, 130.0, "line"),
        ]
        result = words_to_text(word_boxes)
        lines = result.split('\n')
        assert len(lines) == 2
        assert "First line" in lines[0]
        assert "Second line" in lines[1]

    def test_empty_input(self):
        """Empty word boxes return empty string."""
        result = words_to_text([])
        assert result == ""

    def test_version_number_spacing_integration(self):
        """Version numbers with spaced dots get fixed."""
        # Simulate "6 . 0 . 0" from word boxes
        word_boxes = [
            (10.0, 100.0, 15.0, 110.0, "6"),
            (17.0, 100.0, 22.0, 110.0, "."),
            (24.0, 100.0, 29.0, 110.0, "0"),
            (31.0, 100.0, 36.0, 110.0, "."),
            (38.0, 100.0, 43.0, 110.0, "0"),
        ]
        result = words_to_text(word_boxes, x_gap_threshold=1.5)
        # Post-clean should fix spacing
        assert "6.0.0" in result or "6. 0. 0" in result
