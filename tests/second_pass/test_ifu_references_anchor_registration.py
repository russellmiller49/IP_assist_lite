from __future__ import annotations

from medparse.config import get_extraction_config
from medparse.schema.common import EvidenceSpan
from medparse.schema.ifu import IFUDocument, SafetyBlock
from medparse.second_pass.patchers.ifu_references_anchor import apply_ifu_references_anchor
from medparse.second_pass.types import SecondPassContext
from medparse.validate.ifu_rules import validate_ifu
from medparse.validate.validators import ValidationIssue


def test_references_anchor_updates_sections_map() -> None:
    document = IFUDocument(
        source_file="sample.pdf",
        doc_type="ifu",
        page_count=10,
        manufacturer="Sample Manufacturer",
        indications_for_use="Used for demonstration.",
        references=[{"title": "Demo reference"}],
        safety_blocks=[
            SafetyBlock(
                level="warning",
                severity="warning",
                title="WARNING",
                text="Use with care.",
                category="general",
                page=2,
                evidence=EvidenceSpan(text="Use with care.", page=2),
            )
        ],
    )

    paragraph_store = {
        "p1": {"text": "Appendix", "page": 4, "order": [0]},
        "p2": {"text": "References", "page": 9, "order": [1]},
        "p3": {"text": "1. Example citation", "page": 9, "order": [2]},
    }

    ctx = SecondPassContext(
        validation_issues=[
            ValidationIssue("References detected for IFU – ensure a proper References/Bibliography anchor exists.", severity="warning")
        ],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={"ifu": {"references_anchor": {"tail_pages": 2}}},
        mode="always",
        doc_metrics={"extracted_chars": 1200},
        max_runtime_ms=2500,
    )

    result = apply_ifu_references_anchor(document, ctx)
    assert result.applied

    sections = document.pipeline_info.get("sections")
    assert isinstance(sections, dict)
    references_section = sections.get("references")
    assert isinstance(references_section, dict)
    assert references_section.get("page_span") == [9, 9]
    assert references_section.get("source") == "second_pass:references_anchor_backfill"
    assert references_section.get("evidence_ids")

    extraction_config = get_extraction_config()
    issues = validate_ifu(document, extraction_config)
    assert "References detected but references section anchor missing." not in {issue.message for issue in issues}
