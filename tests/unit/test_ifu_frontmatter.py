"""Unit tests for IFU front-matter extraction."""

import pytest

from medparse.normalize.ifu_frontmatter import parse_front_matter


class TestDateExtraction:
    """Test publication date extraction with various formats."""

    def test_compact_date_format(self):
        """Test compact YYYY.MM format."""
        pages = ["PN 553990-11 Rev C 2024.08"]
        result = parse_front_matter(pages)
        assert result["publication_date"] == "2024-08-01"

    def test_spaced_date_format(self):
        """Test spaced 'YYYY . MM' format from word assembly."""
        pages = ["PN 553990-11 Rev C 2024 . 08"]
        result = parse_front_matter(pages)
        assert result["publication_date"] == "2024-08-01"

    def test_hyphenated_date_format(self):
        """Test YYYY-MM format."""
        pages = ["Part Number: 553990-11 Revision: C Date: 2024-08"]
        result = parse_front_matter(pages)
        assert result["publication_date"] == "2024-08-01"

    def test_spaced_hyphenated_date(self):
        """Test spaced 'YYYY - MM' format."""
        pages = ["PN 553990-11 Rev C 2024 - 08"]
        result = parse_front_matter(pages)
        assert result["publication_date"] == "2024-08-01"

    def test_slash_date_format(self):
        """Test YYYY/MM format."""
        pages = ["PN 553990-11 Rev C 2024/08"]
        result = parse_front_matter(pages)
        assert result["publication_date"] == "2024-08-01"

    def test_spaced_slash_date(self):
        """Test spaced 'YYYY / MM' format."""
        pages = ["PN 553990-11 Rev C 2024 / 08"]
        result = parse_front_matter(pages)
        assert result["publication_date"] == "2024-08-01"

    def test_month_name_format(self):
        """Test 'Month YYYY' format."""
        pages = ["PN 553990-11 Rev C August 2024"]
        result = parse_front_matter(pages)
        assert result["publication_date"] == "2024-08-01"

    def test_abbreviated_month_format(self):
        """Test abbreviated month format."""
        pages = ["PN 553990-11 Rev C Aug 2024"]
        result = parse_front_matter(pages)
        assert result["publication_date"] == "2024-08-01"

    def test_concatenated_cover_line(self):
        """Test concatenated cover line: PN553990-11Rev.C2024.08"""
        pages = ["PN553990-11Rev.C2024.08"]
        result = parse_front_matter(pages)
        # PN should be extracted
        assert result["part_number"] == "553990-11"
        # Rev should be extracted
        assert result["revision"] == "Rev C"
        # Date should be extracted
        assert result["publication_date"] == "2024-08-01"

    def test_no_date_returns_none(self):
        """Missing date returns None."""
        pages = ["PN 553990-11 Rev C"]
        result = parse_front_matter(pages)
        assert result["publication_date"] is None


class TestPartNumberExtraction:
    """Test part number extraction."""

    def test_basic_pn_format(self):
        """Test 'PN: 553990-11' format."""
        pages = ["PN: 553990-11"]
        result = parse_front_matter(pages)
        assert result["part_number"] == "553990-11"

    def test_part_number_label(self):
        """Test 'Part Number: 553990-11' format."""
        pages = ["Part Number: 553990-11"]
        result = parse_front_matter(pages)
        assert result["part_number"] == "553990-11"

    def test_pn_without_colon(self):
        """Test 'PN 553990-11' format."""
        pages = ["PN 553990-11"]
        result = parse_front_matter(pages)
        assert result["part_number"] == "553990-11"

    def test_pn_contamination_with_rev(self):
        """Test PN extraction doesn't include Rev suffix."""
        pages = ["PN553990-11Rev.C"]
        result = parse_front_matter(pages)
        # Should extract just the digits-hyphen-digits
        assert result["part_number"] == "553990-11"
        assert "Rev" not in result["part_number"]


class TestRevisionExtraction:
    """Test revision extraction."""

    def test_basic_rev_format(self):
        """Test 'Rev C' format."""
        pages = ["Rev C"]
        result = parse_front_matter(pages)
        assert result["revision"] == "Rev C"

    def test_revision_with_dot(self):
        """Test 'Rev. C' format."""
        pages = ["Rev. C"]
        result = parse_front_matter(pages)
        assert result["revision"] == "Rev C"

    def test_revision_no_space(self):
        """Test 'RevC' format."""
        pages = ["RevC"]
        result = parse_front_matter(pages)
        assert result["revision"] == "Rev C"

    def test_revision_full_word(self):
        """Test 'Revision C' format."""
        pages = ["Revision C"]
        result = parse_front_matter(pages)
        assert result["revision"] == "Rev C"


class TestModelExtraction:
    """Test model extraction."""

    def test_basic_model_format(self):
        """Test 'Model: IF1000' format."""
        pages = ["Model: IF1000"]
        result = parse_front_matter(pages)
        assert result["model"] == "IF1000"

    def test_model_with_hyphen(self):
        """Test 'Model: IF-1000' format."""
        pages = ["Model: IF-1000"]
        result = parse_front_matter(pages)
        assert result["model"] == "IF1000"

    def test_model_with_spaces(self):
        """Test 'Model: IF 1000' format."""
        pages = ["Model: IF 1000"]
        result = parse_front_matter(pages)
        assert result["model"] == "IF1000"


class TestManufacturerExtraction:
    """Test manufacturer extraction."""

    def test_full_manufacturer_name(self):
        """Test full 'Intuitive Surgical, Inc.' format."""
        pages = ["Manufacturer: Intuitive Surgical, Inc."]
        result = parse_front_matter(pages)
        assert result["manufacturer"] == "Intuitive Surgical, Inc."

    def test_manufacturer_no_comma(self):
        """Test 'Intuitive Surgical Inc.' format."""
        pages = ["Intuitive Surgical Inc."]
        result = parse_front_matter(pages)
        assert result["manufacturer"] == "Intuitive Surgical, Inc."

    def test_manufacturer_in_back_pages(self):
        """Test manufacturer detection in back pages."""
        pages = ["PN 553990-11", "", "Intuitive Surgical, Inc."]
        result = parse_front_matter(pages)
        assert result["manufacturer"] == "Intuitive Surgical, Inc."


class TestProductNameExtraction:
    """Test product name extraction."""

    def test_device_name_anchor(self):
        """Test 'Device Name: ...' anchor."""
        pages = ["Device Name: Ion Endoluminal System (Model IF1000)"]
        result = parse_front_matter(pages)
        assert "Ion Endoluminal System" in result["product_name"]

    def test_fallback_ion_system(self):
        """Test fallback detection of 'ion endoluminal system'."""
        pages = ["The ion endoluminal system is used for..."]
        result = parse_front_matter(pages)
        assert result["product_name"] == "Intuitive Ion Endoluminal System"


class TestWindowedSearch:
    """Test windowed search behavior."""

    def test_front_pages_only(self):
        """Test extraction from front pages (0-3)."""
        pages = [
            "PN 553990-11 Rev C",  # Page 0
            "Model IF1000",         # Page 1
            "2024.08",              # Page 2
            "Body text",            # Page 3 (excluded)
            "Body text",            # Page 4
        ]
        result = parse_front_matter(pages)
        assert result["part_number"] == "553990-11"
        assert result["model"] == "IF1000"
        assert result["publication_date"] == "2024-08-01"

    def test_back_pages_fallback(self):
        """Test back pages fallback for manufacturer."""
        pages = [
            "PN 553990-11",
            "Body text",
            "Body text",
            "Body text",
            "Intuitive Surgical, Inc.",  # Last page
        ]
        result = parse_front_matter(pages)
        assert result["manufacturer"] == "Intuitive Surgical, Inc."

    def test_empty_pages(self):
        """Test empty pages list."""
        result = parse_front_matter([])
        assert result["part_number"] is None
        assert result["revision"] is None
        assert result["publication_date"] is None
        assert result["model"] is None
        assert result["manufacturer"] is None
        assert result["product_name"] is None


class TestIntegrationCases:
    """Test complete extraction scenarios."""

    def test_ion_manual_cover_page(self):
        """Test Ion manual cover page extraction."""
        pages = [
            """
            Ion Endoluminal System, Instruments, and Accessories
            User Manual
            PN 553990-11 Rev C 2024.08
            Model IF1000
            Intuitive Surgical, Inc.
            Device Name: Ion Endoluminal System
            Rx only
            """
        ]
        result = parse_front_matter(pages)
        assert result["part_number"] == "553990-11"
        assert result["revision"] == "Rev C"
        assert result["publication_date"] == "2024-08-01"
        assert result["model"] == "IF1000"
        assert result["manufacturer"] == "Intuitive Surgical, Inc."
        assert "Ion Endoluminal System" in result["product_name"]

    def test_concatenated_cover_line(self):
        """Test concatenated cover line parsing."""
        pages = ["PN553990-11Rev.C2024.08 IF1000 Intuitive Surgical, Inc."]
        result = parse_front_matter(pages)
        assert result["part_number"] == "553990-11"
        assert result["revision"] == "Rev C"
        assert result["publication_date"] == "2024-08-01"
        assert result["model"] == "IF1000"
        assert result["manufacturer"] == "Intuitive Surgical, Inc."
