"""Unit tests for software version filtering and normalization."""

import pytest

from medparse.normalize.software import filter_software_versions, _normalize_version


class TestNormalizeVersion:
    """Test version string normalization."""

    def test_spaced_version_numbers(self):
        """Fix '6. 0. 0' → '6.0.0'"""
        text = "Ion OS v 6. 0. 0"
        result = _normalize_version(text)
        assert "6.0.0" in result
        assert ". 0" not in result

    def test_extra_digits_before_v(self):
        """Remove extra digits before 'v': 'Ion OS 1 v 6.0.0' → 'Ion OS v6.0.0'"""
        text = "Ion OS 1 v 6.0.0"
        result = _normalize_version(text)
        assert result == "Ion OS v6.0.0"

    def test_planpoint_software_to_os(self):
        """Canonicalize 'PlanPoint Software' → 'PlanPoint OS'"""
        text = "PlanPoint Software v4.0.0"
        result = _normalize_version(text)
        assert result == "PlanPoint OS v4.0.0"

    def test_ion_os_casing(self):
        """Normalize 'ion os' → 'Ion OS'"""
        text = "ion os v6.0.0"
        result = _normalize_version(text)
        assert result == "Ion OS v6.0.0"

    def test_planpoint_os_casing(self):
        """Normalize 'planpoint os' → 'PlanPoint OS'"""
        text = "planpoint os v4.0"
        result = _normalize_version(text)
        assert result == "PlanPoint OS v4.0"

    def test_multiple_spaces_collapsed(self):
        """Collapse multiple spaces."""
        text = "Ion  OS    v6.0.0"
        result = _normalize_version(text)
        assert "  " not in result
        assert result == "Ion OS v6.0.0"

    def test_concatenated_version(self):
        """Handle concatenated 'IonOS1v6.0.0' format."""
        text = "IonOS1v6.0.0"
        result = _normalize_version(text)
        assert result == "Ion OS v6.0.0"

    def test_version_with_extra_whitespace(self):
        """Clean up extra whitespace around version."""
        text = "  Ion OS  v  6. 0. 0  "
        result = _normalize_version(text)
        assert result == "Ion OS v6.0.0"


class TestFilterSoftwareVersions:
    """Test software version filtering with allowlist/denylist."""

    def test_ion_os_allowed(self):
        """Ion OS versions are kept."""
        raw = ["Ion OS v6.0.0", "Ion OS v5.0.1"]
        result = filter_software_versions(raw)
        assert len(result) == 2
        assert "Ion OS v6.0.0" in result
        assert "Ion OS v5.0.1" in result

    def test_planpoint_allowed(self):
        """PlanPoint versions are kept."""
        raw = ["PlanPoint Software v4.0", "PlanPoint OS v3.0"]
        result = filter_software_versions(raw)
        assert len(result) == 2
        assert "PlanPoint OS v4.0" in result  # Software → OS
        assert "PlanPoint OS v3.0" in result

    def test_ffmpeg_denied(self):
        """FFmpeg entries are filtered out."""
        raw = ["Ion OS v6.0.0", "FFmpeg 4.3.1", "libavcodec"]
        result = filter_software_versions(raw)
        assert len(result) == 1
        assert result[0] == "Ion OS v6.0.0"

    def test_lgpl_denied(self):
        """LGPL entries are filtered out."""
        raw = ["Ion OS v6.0.0", "LGPL v2.1", "GPL v3"]
        result = filter_software_versions(raw)
        assert len(result) == 1
        assert result[0] == "Ion OS v6.0.0"

    def test_openssl_denied(self):
        """OpenSSL entries are filtered out."""
        raw = ["Ion OS v6.0.0", "OpenSSL 1.1.1", "libssl"]
        result = filter_software_versions(raw)
        assert len(result) == 1
        assert result[0] == "Ion OS v6.0.0"

    def test_license_keyword_denied(self):
        """Entries with 'license' are filtered out."""
        raw = ["Ion OS v6.0.0", "See license file", "Licensed under MIT"]
        result = filter_software_versions(raw)
        assert len(result) == 1
        assert result[0] == "Ion OS v6.0.0"

    def test_third_party_denied(self):
        """Third-party entries are filtered out."""
        raw = ["Ion OS v6.0.0", "Third-party libraries", "third party code"]
        result = filter_software_versions(raw)
        assert len(result) == 1
        assert result[0] == "Ion OS v6.0.0"

    def test_package_library_denied(self):
        """Package/library entries are filtered out."""
        raw = ["Ion OS v6.0.0", "Package: numpy", "Library: OpenCV"]
        result = filter_software_versions(raw)
        assert len(result) == 1
        assert result[0] == "Ion OS v6.0.0"

    def test_normalization_applied(self):
        """Normalization is applied to kept entries."""
        raw = ["Ion OS 1 v 6. 0. 0", "PlanPoint Software v 4. 0"]
        result = filter_software_versions(raw)
        assert len(result) == 2
        assert result[0] == "Ion OS v6.0.0"
        assert result[1] == "PlanPoint OS v4.0"

    def test_deduplication(self):
        """Duplicate entries are removed."""
        raw = ["Ion OS v6.0.0", "Ion OS v6.0.0", "Ion OS v5.0"]
        result = filter_software_versions(raw)
        assert len(result) == 2
        assert result.count("Ion OS v6.0.0") == 1

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert filter_software_versions([]) == []
        assert filter_software_versions(None) == []

    def test_non_string_entries_skipped(self):
        """Non-string entries are skipped."""
        raw = ["Ion OS v6.0.0", None, 123, "PlanPoint OS v4.0"]
        result = filter_software_versions(raw)
        assert len(result) == 2
        assert "Ion OS v6.0.0" in result
        assert "PlanPoint OS v4.0" in result


class TestIntegrationScenarios:
    """Test real-world extraction scenarios."""

    def test_ion_manual_software_section(self):
        """Test Ion manual Equipment and Software Version section."""
        raw = [
            "Equipment and Software Version",
            "Ion OS 1 v 6. 0. 0",
            "PlanPoint Software v 4. 0",
            "FFmpeg 4.3.1",
            "OpenSSL 1.1.1k",
            "LGPL v2.1",
            "See license file for third-party libraries",
        ]
        result = filter_software_versions(raw)
        assert len(result) == 2
        assert "Ion OS v6.0.0" in result
        assert "PlanPoint OS v4.0" in result
        # Ensure no noise entries
        assert not any("FFmpeg" in s for s in result)
        assert not any("OpenSSL" in s for s in result)
        assert not any("LGPL" in s for s in result)
        assert not any("license" in s.lower() for s in result)

    def test_concatenated_software_lines(self):
        """Test concatenated software lines from word assembly."""
        raw = [
            "IonOS1v6.0.0",
            "PlanPointSoftwarev4.0",
        ]
        result = filter_software_versions(raw)
        assert len(result) == 2
        assert "Ion OS v6.0.0" in result
        assert "PlanPoint OS v4.0" in result

    def test_mixed_case_and_spacing(self):
        """Test mixed case and spacing variations."""
        raw = [
            "ion os v 6. 0. 0",
            "PLANPOINT SOFTWARE V 4. 0",
            "Ion  OS    v5.0",
        ]
        result = filter_software_versions(raw)
        assert len(result) == 3
        assert "Ion OS v6.0.0" in result
        assert "PlanPoint OS v4.0" in result
        assert "Ion OS v5.0" in result

    def test_realistic_mixed_content(self):
        """Test realistic mix of product and noise entries."""
        raw = [
            "Equipment and Software Version",
            "Product software:",
            "Ion OS v6.0.0",
            "PlanPoint OS v4.0",
            "",
            "Third-party components:",
            "FFmpeg (LGPL v2.1)",
            "OpenSSL (Apache License)",
            "See LICENSES folder for details",
        ]
        result = filter_software_versions(raw)
        assert len(result) == 2
        assert result == ["Ion OS v6.0.0", "PlanPoint OS v4.0"]
