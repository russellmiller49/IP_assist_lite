from __future__ import annotations

from medparse.schema.article import ArticleDocument
from medparse.second_pass.patchers.article_yield_strict_miner import apply_article_yield_strict_miner
from medparse.second_pass.types import SecondPassContext
from medparse.validate.validators import ValidationIssue


def _make_context(paragraph_store, mode: str = "always") -> SecondPassContext:
    return SecondPassContext(
        validation_issues=[ValidationIssue("Diagnostic yield missing for research article")],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={},
        mode=mode,
        doc_metrics={},
        max_runtime_ms=2500,
    )


def test_article_yield_strict_miner_extracts_counts() -> None:
    document = ArticleDocument(
        source_file="synthetic.pdf",
        page_count=1,
        doc_subtype="research_diagnostic",
    )
    document.pipeline_info = {}
    paragraph_store = {
        "hash1": {
            "text": "Diagnostic yield was 64% (32/50) for peripheral lesions.",
            "page": 5,
            "order": [10],
        }
    }
    ctx = _make_context(paragraph_store)

    result = apply_article_yield_strict_miner(document, ctx)
    assert result.applied

    diagnostic = document.diagnostic_yield
    assert diagnostic is not None
    assert diagnostic.numerator == 32
    assert diagnostic.denominator == 50
    assert diagnostic.strict is True
    assert diagnostic.compatible_with_ats is True
    assert diagnostic.exclusion_reasons == []
    assert diagnostic.value is not None and abs(diagnostic.value - 64.0) < 1e-6
    assert diagnostic.evidence_refs == ["hash1"]

    payload = document.pipeline_info.get("ats_yield")
    assert payload is not None
    assert payload["strict_yield"] is True
    assert payload["n"] == 32
    assert payload["N"] == 50
    assert payload["reasons"] == []


def test_article_yield_strict_miner_flags_missing_counts() -> None:
    document = ArticleDocument(
        source_file="synthetic.pdf",
        page_count=1,
        doc_subtype="research_diagnostic",
    )
    document.pipeline_info = {}
    paragraph_store = {
        "hash1": {
            "text": "The diagnostic yield was 64% for procedures without detailed counts.",
            "page": 3,
            "order": [15],
        }
    }
    ctx = _make_context(paragraph_store)

    result = apply_article_yield_strict_miner(document, ctx)
    assert result.applied

    diagnostic = document.diagnostic_yield
    assert diagnostic is not None
    assert diagnostic.strict is False
    assert diagnostic.compatible_with_ats is False
    assert "derived_counts_from_percent" in diagnostic.exclusion_reasons
    assert "no_n_over_N" in diagnostic.exclusion_reasons

    payload = document.pipeline_info.get("ats_yield")
    assert payload is not None
    assert payload["strict_yield"] is False
    reasons = payload.get("reasons", [])
    assert "derived_counts_from_percent" in reasons
    assert "no_n_over_N" in reasons
