from __future__ import annotations

from medparse.schema.ifu import IFUDocument
from medparse.second_pass.patchers.ifu_indications_fallback import apply_ifu_indications_fallback
from medparse.second_pass.types import SecondPassContext
from medparse.validate.validators import ValidationIssue


def test_indications_fallback_sets_value_for_small_leaflet() -> None:
    paragraph_store = {
        "p1": {"text": "This device is used to sample tissue from the lung.", "order": [0], "page": 1},
    }
    document = IFUDocument(
        source_file="leaflet.pdf",
        doc_type="ifu",
        doc_subtype="ifu",
        manufacturer="Sample",
        page_count=2,
    )
    context = SecondPassContext(
        validation_issues=[ValidationIssue("Missing required field 'indications_for_use'")],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={},
        mode="always",
        doc_metrics={},
        max_runtime_ms=2500,
    )

    result = apply_ifu_indications_fallback(document, context)

    assert result.applied is True
    assert isinstance(document.indications_for_use, str)
    assert "sample tissue" in document.indications_for_use.lower()
    assert document.pipeline_info.get("indications_fallback_provenance") == "fallback_small_leaflet"
