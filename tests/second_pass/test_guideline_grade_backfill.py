from __future__ import annotations

from medparse.schema.article import ArticleDocument, GuidelineRecommendation
from medparse.second_pass.patchers.guideline_grade_backfill import apply_guideline_grade_backfill
from medparse.second_pass.types import SecondPassContext
from medparse.validate.validators import ValidationIssue


def test_guideline_grade_backfill_populates_code_and_strength() -> None:
    recommendation = GuidelineRecommendation(
        text="We recommend performing bronchoscopy in symptomatic patients.",
        anchors=["r1"],
        evidence_refs=["r1"],
    )
    best_practice = GuidelineRecommendation(
        text="Best Practice Statement: clinicians should provide counselling.",
        anchors=["r2"],
        evidence_refs=["r2"],
    )
    ungraded = GuidelineRecommendation(
        text="Clinicians may consider additional follow-up.",
        anchors=["r3"],
        evidence_refs=["r3"],
    )

    paragraph_store = {
        "r1": {"text": "Strong recommendation with Grade 1A (high certainty)", "order": [0], "page": 5},
        "r2": {"text": "Best Practice Statement for perioperative care", "order": [1], "page": 6},
        "r3": {"text": "No grade specified", "order": [2], "page": 7},
    }

    document = ArticleDocument(
        source_file="guideline.pdf",
        doc_type="article",
        doc_subtype="guideline",
        title="Guideline",
        sections={},
        recommendations=[recommendation, best_practice, ungraded],
    )
    context = SecondPassContext(
        validation_issues=[ValidationIssue("Guideline recommendations missing grade/ungraded tag for >=30% of entries.")],
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

    result = apply_guideline_grade_backfill(document, context)

    assert result.applied is True
    assert document.pipeline_info.get("grade_backfilled") == 1
    assert document.pipeline_info.get("recommendations_retyped") == 2

    updated = document.recommendations[0]
    assert updated.grade == "1A"
    assert updated.strength == "strong"
    assert updated.evidence_level == "high"

    best_practice_updated = document.recommendations[1]
    assert best_practice_updated.statement_type == "consensus"
    assert best_practice_updated.ungraded is True

    ungraded_updated = document.recommendations[2]
    assert ungraded_updated.ungraded is True
    assert ungraded_updated.ungraded_reason == "no_grade_phrase_found"
    assert ungraded_updated.statement_type == "ungraded"
