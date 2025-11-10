from __future__ import annotations

from medparse.schema.ifu import IFUDocument
from medparse.validate.validators import ValidationIssue
from medparse.second_pass.patchers.ifu_frontmatter_backfill import apply_ifu_frontmatter_backfill
from medparse.second_pass.types import SecondPassContext


def _make_context(paragraph_store: dict, mode: str = "always", config: dict | None = None) -> SecondPassContext:
    return SecondPassContext(
        validation_issues=[],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config=config or {},
        mode=mode,
        doc_metrics={},
        max_runtime_ms=2500,
    )


def test_alt_pro_frontmatter_backfill_recovers_model_and_revision() -> None:
    document = IFUDocument(
        doc_type="ifu",
        doc_subtype="ifu",
        source_file="ALT-Pro_Instruction Manual.pdf",
        page_count=6,
        manufacturer="Olympus Corporation",
    )
    document.pipeline_info = {}

    paragraph_store = {
        "p1": {
            "text": "ALT-PRO Bronchoscope\nALT PRO",
            "page": 1,
            "order": [1],
        },
        "p2": {
            "text": "Revision: D",
            "page": 1,
            "order": [2],
        },
    }

    ctx = _make_context(paragraph_store)
    result = apply_ifu_frontmatter_backfill(document, ctx)

    assert result.applied
    assert document.model == "ALT PRO"
    assert document.revision == "D"

    meta = document.pipeline_info.get("second_pass", {}).get("meta", {})
    assert meta.get("front_matter_model") == 1
    assert meta.get("front_matter_revision") == 1
    front_meta = document.pipeline_info.get("front_matter_meta", {})
    assert front_meta.get("revision_status") == "extracted"
    assert front_meta.get("revision_provenance") == "extracted"


def test_unknown_vendor_footer_inference_backfills_manufacturer_and_date() -> None:
    document = IFUDocument(
        doc_type="ifu",
        doc_subtype="ifu",
        source_file="403000001-003.pdf",
        page_count=3,
    )
    document.pipeline_info = {}

    paragraph_store = {
        "p1": {
            "text": "© 2021 Example Medical Inc.\nhttps://www.examplemedical.com\nPublished July 2021",
            "page": 1,
            "order": [1],
        },
        "p2": {
            "text": "Example Medical Inc. All rights reserved.",
            "page": 2,
            "order": [10],
        },
    }

    ctx = _make_context(paragraph_store)
    result = apply_ifu_frontmatter_backfill(document, ctx)

    assert result.applied
    assert document.manufacturer == "Example Medical Inc"
    assert document.publication_date == "2021-07"

    meta = document.pipeline_info.get("second_pass", {}).get("meta", {})
    assert meta.get("front_matter_manufacturer") == 1
    assert meta.get("front_matter_publication_date") == 1


def test_channel_brush_template_and_revision_sanitized() -> None:
    document = IFUDocument(
        doc_type="ifu",
        doc_subtype="ifu",
        source_file="BW-18V_Instruction_Manual.pdf",
        page_count=2,
        product_name="INSTRUCTIONS USA",
        revision="ACUUM",
    )
    document.pipeline_info = {}

    paragraph_store = {
        "a": {
            "text": "INSTRUCTIONS USA\nCHANNEL CLEANING BRUSH",
            "page": 1,
            "order": [1],
        },
        "b": {
            "text": "BW-18V Channel Cleaning Brush",
            "page": 1,
            "order": [2],
        },
        "c": {
            "text": "Date of Issue 2022-01-15",
            "page": 2,
            "order": [3],
        },
        "d": {
            "text": "GR1234 05",
            "page": 2,
            "order": [4],
        },
    }

    config = {
        "ifu": {
            "frontmatter": {
                "drop_headings_as_product": ["INSTRUCTIONS", "INSTRUCTIONS USA"],
                "vendor_heuristics": {
                    "olympus": {
                        "manufacturer": "Olympus Corporation",
                        "product_name_template": "{manufacturer} {part_number} {model}",
                        "print_code_pattern": "GR\\d{4}\\s*\\d{2}",
                    }
                },
            }
        }
    }

    ctx = _make_context(paragraph_store, config=config)
    result = apply_ifu_frontmatter_backfill(document, ctx)

    assert result.applied
    assert document.manufacturer == "Olympus Corporation"
    assert document.part_number == "BW-18V"
    assert document.model == "Channel Cleaning Brush"
    assert document.product_name == "Olympus BW-18V Channel Cleaning Brush"
    assert document.revision is None
    meta = document.pipeline_info.get("front_matter_meta", {})
    assert meta.get("print_code") == "GR1234 05"
    assert document.pipeline_info.get("front_matter_revision_sanitized") is True
    warnings = document.pipeline_info.get("threshold_warnings") or []
    assert "front_matter_revision_sanitized" in warnings
    assert document.pipeline_info.get("revision_status") == "sanitized_unusable"
    assert meta.get("revision_provenance") == "sanitized"
