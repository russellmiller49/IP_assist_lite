from __future__ import annotations

from medparse.schema.ifu import IFUDocument
from medparse.second_pass.patchers.ifu_sectionizer_salvage import apply_ifu_sectionizer_salvage
from medparse.second_pass.types import SecondPassContext


def _make_context(paragraph_store: dict) -> SecondPassContext:
    return SecondPassContext(
        validation_issues=[],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={"ifu": {"anchors": {"sectionizer_extra": ["Important Information", "Signal words"]}}},
        mode="always",
        doc_metrics={},
        max_runtime_ms=2500,
    )


def test_sectionizer_salvage_builds_headings() -> None:
    document = IFUDocument(doc_type="ifu", doc_subtype="ifu", page_count=4, source_file="section.pdf")
    document.pipeline_info = {}
    paragraph_store = {
        "p1": {"text": "Chapter 1 Important Information", "page": 1, "order": [1]},
        "p2": {"text": "Chapter 2 Signal words", "page": 2, "order": [2]},
    }

    ctx = _make_context(paragraph_store)
    result = apply_ifu_sectionizer_salvage(document, ctx)

    assert result.applied
    assert result.reasons[0].startswith("section_salvage_ifu")
    sections = document.pipeline_info.get("sections", {})
    assert sections
    assert "Chapter 1 Important Information" in sections
