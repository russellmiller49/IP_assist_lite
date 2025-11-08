from __future__ import annotations

from medparse.schema.ifu import IFUDocument
from medparse.second_pass.patchers.ifu_toc_bleed_guard import apply_ifu_toc_bleed_guard
from medparse.second_pass.types import SecondPassContext
from medparse.validate.validators import ValidationIssue


def test_toc_bleed_guard_shifts_anchor_forward() -> None:
    paragraph_store = {
        "toc1": {"text": "1. Introduction ........ 4", "order": [0], "page": 1},
        "toc2": {"text": "1.1 Safety ........ 5", "order": [1], "page": 1},
    }

    document = IFUDocument(
        source_file="ifu.pdf",
        doc_type="ifu",
        doc_subtype="ifu",
        manufacturer="Intuitive",
        page_count=10,
    )
    document.pipeline_info.setdefault("sections", {
        "section_1": {"title": "Clinical Use", "start_page": 1},
        "section_2": {"title": "Safety", "start_page": 2},
    })
    context = SecondPassContext(
        validation_issues=[ValidationIssue("Clinical anchor bleed detected")],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={"toc_guard": {"min_hits": 1}},
        mode="always",
        doc_metrics={},
        max_runtime_ms=2500,
    )

    result = apply_ifu_toc_bleed_guard(document, context)

    assert result.applied is True
    sections = document.pipeline_info.get("sections", {})
    assert sections["section_1"]["start_page"] == 2
    assert document.pipeline_info.get("toc_guard_adjustments") == 1
