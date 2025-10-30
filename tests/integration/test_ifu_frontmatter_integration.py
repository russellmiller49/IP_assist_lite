"""Integration tests for IFU front-matter extraction."""

import json
from pathlib import Path

import pytest

from medparse.extractors.ifu import extract_ifu
from medparse.validate.validators import validate_document


@pytest.fixture
def ion_ifu_pdf():
    """Path to Ion IFU PDF."""
    pdf_path = Path("data/seed/Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf")
    if not pdf_path.exists():
        pytest.skip(f"Ion IFU PDF not found at {pdf_path}")
    return pdf_path


@pytest.fixture
def golden_data():
    """Load golden data for Ion IFU."""
    golden_path = Path("tests/golden/ion_ifu_frontmatter_golden.json")
    if not golden_path.exists():
        pytest.skip(f"Golden data not found at {golden_path}")
    with open(golden_path) as f:
        return json.load(f)


def test_ion_ifu_front_matter(ion_ifu_pdf, golden_data):
    """Test that front-matter extraction matches golden data."""
    doc = extract_ifu(ion_ifu_pdf, engine="pymupdf")

    # Check all front-matter fields
    assert doc.part_number == golden_data["part_number"], "Part number mismatch"
    assert doc.revision == golden_data["revision"], "Revision mismatch"
    assert doc.publication_date == golden_data["publication_date"], "Publication date mismatch"
    assert doc.model == golden_data["model"], "Model mismatch"
    assert doc.manufacturer == golden_data["manufacturer"], "Manufacturer mismatch"
    assert doc.product_name == golden_data["product_name"], "Product name mismatch"

    # Check software versions
    assert doc.software_versions == golden_data["software_versions"], "Software versions mismatch"

    # Check safety block count (allow some variance)
    assert abs(len(doc.safety_blocks) - golden_data["safety_block_count"]) < 10, (
        f"Safety block count mismatch: expected ~{golden_data['safety_block_count']}, got {len(doc.safety_blocks)}"
    )

    # Check page count
    assert doc.page_count == golden_data["page_count"], "Page count mismatch"


def test_ion_ifu_validation(ion_ifu_pdf):
    """Test that Ion IFU passes validation with no errors."""
    doc = extract_ifu(ion_ifu_pdf, engine="pymupdf")
    issues = validate_document(doc, min_safety_blocks=20)

    # Should have no errors
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 0, f"Validation errors: {[e.message for e in errors]}"


def test_ion_ifu_acceptance_criteria(ion_ifu_pdf):
    """Test Ion IFU against detailed acceptance criteria."""
    doc = extract_ifu(ion_ifu_pdf, engine="pymupdf")

    # Required fields must be present
    assert doc.part_number == "553990-11", f"Expected PN 553990-11, got {doc.part_number}"
    assert doc.revision == "Rev C", f"Expected Rev C, got {doc.revision}"
    assert doc.publication_date == "2024-08-01", f"Expected 2024-08-01, got {doc.publication_date}"
    assert doc.model == "IF1000", f"Expected IF1000, got {doc.model}"
    assert doc.manufacturer == "Intuitive Surgical, Inc.", f"Expected Intuitive Surgical, Inc., got {doc.manufacturer}"
    assert doc.product_name == "Intuitive Ion Endoluminal System", (
        f"Expected 'Intuitive Ion Endoluminal System', got {doc.product_name}"
    )

    # Software versions should be clean
    assert len(doc.software_versions) > 0, "No software versions found"
    for ver in doc.software_versions:
        assert "Ion OS" in ver or "Plan Point" in ver, f"Unexpected software version: {ver}"
        assert "FFmpeg" not in ver, "Found noise (FFmpeg) in software versions"
        assert "LGPL" not in ver, "Found noise (LGPL) in software versions"

    # Safety blocks should be clean
    assert len(doc.safety_blocks) >= 20, f"Expected at least 20 safety blocks, got {len(doc.safety_blocks)}"

    # Check first few safety blocks for footer noise
    for i, block in enumerate(doc.safety_blocks[:10]):
        assert "IonSystem,Instruments,andAccessoriesUserManual" not in block.text, (
            f"Found footer noise in safety block {i}"
        )
        assert "EndofSection" not in block.text, f"Found section marker in safety block {i}"
