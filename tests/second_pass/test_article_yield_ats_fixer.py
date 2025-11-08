from __future__ import annotations

from medparse.schema.article import ArticleDocument
from medparse.second_pass.patchers.article_yield_ats_fixer import apply_yield_ats_fixer
from medparse.second_pass.types import SecondPassContext
from medparse.validate.validators import ValidationIssue


def _build_article(paragraphs: dict[str, dict[str, object]]) -> tuple[ArticleDocument, SecondPassContext]:
    document = ArticleDocument(
        source_file="sample.pdf",
        doc_type="article",
        doc_subtype="research",
        title="Test Study",
        sections={},
    )
    context = SecondPassContext(
        validation_issues=[ValidationIssue("Diagnostic yield missing for research article")],
        paragraph_store=paragraphs,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={"yield_ats": {"max_proximity_paras": 2}},
        mode="always",
        doc_metrics={},
        max_runtime_ms=2500,
    )
    return document, context


def test_yield_from_percent_sets_reason_and_non_strict() -> None:
    paragraphs = {
        "p1": {"text": "Overall diagnostic yield was 58%", "order": [0], "page": 1},
    }
    document, context = _build_article(paragraphs)

    result = apply_yield_ats_fixer(document, context)

    assert result.applied is True
    assert document.diagnostic_yield is not None
    assert document.diagnostic_yield.value == 58.0
    assert document.diagnostic_yield.strict is False
    assert document.diagnostic_yield.compatible_with_ats is False
    reasons = set(document.diagnostic_yield.exclusion_reasons or [])
    assert "derived_counts_from_percent" in reasons


def test_yield_from_counts_extracts_fraction() -> None:
    paragraphs = {
        "p1": {"text": "Results: 32 of 79 patients achieved diagnostic yield", "order": [0], "page": 2},
    }
    document, context = _build_article(paragraphs)

    result = apply_yield_ats_fixer(document, context)

    assert result.applied is True
    assert document.diagnostic_yield is not None
    assert document.diagnostic_yield.numerator == 32
    assert document.diagnostic_yield.denominator == 79
    reasons = set(document.diagnostic_yield.exclusion_reasons or [])
    assert "no_n_over_N" in reasons


def test_follow_up_language_sets_reason() -> None:
    paragraphs = {
        "p1": {
            "text": "Diagnostic yield including subsequent surgery reached 45 of 90 cases",
            "order": [0],
            "page": 3,
        },
    }
    document, context = _build_article(paragraphs)

    result = apply_yield_ats_fixer(document, context)

    assert result.applied is True
    assert document.diagnostic_yield is not None
    reasons = set(document.diagnostic_yield.exclusion_reasons or [])
    assert "follow_up_used_in_numerator" in reasons
