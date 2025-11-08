from __future__ import annotations

from medparse.schema.ifu import IFUDocument
from medparse.second_pass.patchers.ifu_safety_density_booster import apply_ifu_safety_density_booster
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


def test_safety_booster_uses_dynamic_threshold() -> None:
    document = IFUDocument(doc_type="ifu", doc_subtype="ifu", page_count=10, source_file="safety.pdf")
    document.pipeline_info = {"extracted_chars": 6000}

    paragraph_store = {
        "s1": {"text": "WARNING: Do not over-tighten", "page": 2, "order": [1]},
        "s2": {"text": "CAUTION: Inspect the brush", "page": 2, "order": [2]},
        "s3": {"text": "NOTE: Replace damaged components", "page": 3, "order": [3]},
    }

    config = {
        "ifu": {
            "safety": {
                "dynamic_threshold": {"min_short": 8, "cap_long": 20, "chars_per_10": 50000},
                "booster": {"dedupe_ratio": 0.8, "max_added": 5},
            }
        }
    }

    ctx = _make_context(paragraph_store, config=config)
    result = apply_ifu_safety_density_booster(document, ctx)

    assert result.applied
    assert "safety_density_boost" in result.reasons[0]
    assert document.pipeline_info.get("safety_blocks_found") == len(document.safety_blocks)
    assert document.pipeline_info.get("safety_density_boost_detail")
    detail = document.pipeline_info["safety_density_boost_detail"][0]
    assert detail["expected"] == 8
    assert detail["found_after"] == len(document.safety_blocks)


def test_safety_booster_page_guard_applies() -> None:
    document = IFUDocument(doc_type="ifu", doc_subtype="ifu", page_count=45, source_file="guard.pdf")
    document.pipeline_info = {"extracted_chars": 1000}
    paragraph_store = {
        "s1": {"text": "WARNING: Handle carefully", "page": 5, "order": [1]},
        "s2": {"text": "CAUTION: Follow procedures", "page": 6, "order": [2]},
        "s3": {"text": "NOTE: Refer to manual", "page": 7, "order": [3]},
    }
    ctx = _make_context(paragraph_store)
    result = apply_ifu_safety_density_booster(document, ctx)
    assert result.applied
    detail = document.pipeline_info["safety_density_boost_detail"][0]
    assert detail["expected"] == 15  # clamp(pages/3, 8, 20) => ceil(15)


def test_safety_booster_limits_added_blocks_by_candidates() -> None:
    document = IFUDocument(doc_type="ifu", doc_subtype="ifu", page_count=12, source_file="limit.pdf")
    document.pipeline_info = {"extracted_chars": 2000}
    paragraph_store = {
        f"s{idx}": {"text": f"WARNING: Entry {idx}", "page": idx, "order": [idx]}
        for idx in range(1, 11)
    }
    config = {
        "ifu": {
            "safety": {
                "booster": {
                    "dedupe_ratio": 0.99,
                    "max_added": 20,
                }
            }
        }
    }
    ctx = _make_context(paragraph_store, config=config)
    result = apply_ifu_safety_density_booster(document, ctx)
    assert result.applied
    assert document.pipeline_info.get("safety_blocks_added") == 4
    assert result.modifications.get("safety_blocks_added") == 4
