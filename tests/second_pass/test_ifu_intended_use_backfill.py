from __future__ import annotations

from medparse.schema.ifu import IFUDocument
from medparse.second_pass.patchers.ifu_intended_use_backfill import apply_ifu_intended_use_backfill
from medparse.second_pass.types import SecondPassContext


def _make_context(paragraph_store: dict, config: dict | None = None) -> SecondPassContext:
    return SecondPassContext(
        validation_issues=[],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config=config or {},
        mode="always",
        doc_metrics={},
        max_runtime_ms=2500,
    )


def test_intended_use_and_contraindications_from_important_information() -> None:
    document = IFUDocument(doc_type="ifu", doc_subtype="ifu", page_count=20, source_file="test.pdf")
    document.pipeline_info = {}
    paragraph_store = {
        "p1": {"text": "Important Information — Please Read Before Use", "page": 3, "order": [10]},
        "p2": {"text": "Indications for use: This equipment is intended to perform leakage testing.", "page": 3, "order": [11]},
        "p3": {"text": "Contraindications: None known.", "page": 3, "order": [12]},
    }
    config = {
        "ifu": {
            "anchors": {
                "important_info": ["Important Information — Please Read Before Use"],
                "indications_en": ["Indications for use"],
                "contraindications": ["Contraindications"],
            }
        }
    }

    ctx = _make_context(paragraph_store, config=config)
    result = apply_ifu_intended_use_backfill(document, ctx)

    assert result.applied
    assert document.intended_use.startswith("This equipment is intended")
    assert isinstance(document.indications_for_use, dict)
    assert document.indications_for_use["text"].startswith("This equipment is intended")
    assert document.contraindications == ["None known."]
