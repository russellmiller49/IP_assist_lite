from __future__ import annotations

from medparse.schema.ifu import IFUDocument
from medparse.second_pass.patchers.ifu_small import apply_ifu_small_leaflet_map
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


def test_small_leaflet_bilingual_mapping() -> None:
    document = IFUDocument(doc_type="ifu", doc_subtype="ifu", source_file="BW-18V.pdf")
    paragraph_store = {
        "a": {
            "text": "INTENDED USE: This instrument has been designed to be used for brushing the suction channels of Olympus bronchoscopes. Clean and rinse thoroughly after each use.",
            "page": 1,
            "order": [1],
        },
        "b": {
            "text": "使用目的：本器具はオリンパス気管支鏡の吸引チャンネルをブラッシングするために使用します。すべての洗浄手順を完了してください。",
            "page": 1,
            "order": [2],
        },
    }
    config = {
        "ifu": {
            "anchors": {
                "indications_en": [
                    "INTENDED USE",
                    "Indications for use",
                    "This instrument has been designed to be used",
                ],
                "indications_ja": ["使用目的"],
            }
        }
    }

    ctx = _make_context(paragraph_store, config=config)
    result = apply_ifu_small_leaflet_map(document, ctx)

    assert result.applied
    assert result.reasons == ["small_leaflet_mapper"]
    assert document.intended_use == "This instrument has been designed to be used for brushing the suction channels of Olympus bronchoscopes."
    assert isinstance(document.indications_for_use, dict)
    assert document.indications_for_use["text"] == document.intended_use
    localized = document.pipeline_info.get("localized", {})
    ja_entry = localized.get("indications", {}).get("ja") if isinstance(localized, dict) else None
    assert ja_entry and ja_entry.startswith("本器具は")
