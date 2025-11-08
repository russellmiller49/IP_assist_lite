from __future__ import annotations

from medparse.schema.ifu import IFUDocument
from medparse.validate.validators import ValidationIssue
from medparse.second_pass.patchers.ifu_references_anchor import apply_ifu_references_anchor
from medparse.second_pass.types import SecondPassContext


def _make_context(paragraph_store: dict, validation_message: str) -> SecondPassContext:
    return SecondPassContext(
        validation_issues=[ValidationIssue(validation_message, severity="warning")],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={"ifu": {"references": {"tail_pages": 2}}},
        mode="auto",
        doc_metrics={},
        max_runtime_ms=2500,
    )


def test_references_anchor_backfill_populates_pipeline_info() -> None:
    document = IFUDocument(
        doc_type="ifu",
        doc_subtype="ifu",
        source_file="ion.pdf",
        page_count=10,
    )
    document.references = ["Example reference"]
    document.pipeline_info = {}

    paragraph_store = {
        "tail-1": {"text": "References", "page": 9, "order": [100]},
        "tail-2": {"text": "1. Doe et al.", "page": 9, "order": [101]},
        "tail-3": {"text": "Bibliography", "page": 10, "order": [110]},
    }

    ctx = _make_context(paragraph_store, "References detected for IFU – ensure a proper References/Bibliography anchor exists.")
    result = apply_ifu_references_anchor(document, ctx)

    assert result.applied
    anchor_info = document.pipeline_info.get("references_anchor")
    assert anchor_info is not None
    assert anchor_info["pages"] == [9, 10]
    assert document.pipeline_info.get("references_anchor_backfill") is True

    meta = document.pipeline_info.get("second_pass", {}).get("meta", {})
    assert meta.get("references_anchor_backfill") == 1

    sections = document.pipeline_info.get("sections", {})
    assert isinstance(sections, dict)
    assert "references" in sections
    refs_entry = sections["references"]
    assert refs_entry.get("start_page") == 9
    assert refs_entry.get("end_page") == 10
