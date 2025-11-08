from __future__ import annotations

from medparse.schema.article import ArticleDocument
from medparse.second_pass.patchers.article_section_fix import apply_sectionizer_salvage
from medparse.second_pass.types import SecondPassContext
from medparse.validate.validators import ValidationIssue


def test_sectionizer_salvage_creates_four_sections() -> None:
    paragraph_store = {
        "p1": {"text": "Introduction", "order": [0], "page": 1},
        "p2": {"text": "Introduction content about the study.", "order": [1], "page": 1},
        "p3": {"text": "Methods", "order": [2], "page": 2},
        "p4": {"text": "We conducted a randomized trial.", "order": [3], "page": 2},
        "p5": {"text": "Results", "order": [4], "page": 3},
        "p6": {"text": "Results indicated improved survival.", "order": [5], "page": 3},
        "p7": {"text": "Discussion", "order": [6], "page": 4},
        "p8": {"text": "We discuss the findings and implications.", "order": [7], "page": 4},
    }

    document = ArticleDocument(
        source_file="sample.pdf",
        doc_type="article",
        doc_subtype="research",
        title="Section Salvage",
        sections={},
    )
    context = SecondPassContext(
        validation_issues=[ValidationIssue("Research article has too few sections")],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={"sectionizer": {"min_sections_research": 4}},
        mode="always",
        doc_metrics={"sections_count": 0},
        max_runtime_ms=2500,
    )

    result = apply_sectionizer_salvage(document, context)

    assert result.applied is True
    assert len(document.sections) >= 4
    assert set(document.sections.keys()) >= {"introduction", "methods", "results", "discussion"}


def test_sectionizer_salvage_collapses_duplicate_headings() -> None:
    paragraph_store = {
        "p1": {"text": "Results", "order": [0], "page": 2},
        "p2": {"text": "Primary outcome improved significantly.", "order": [1], "page": 2},
        "p3": {"text": "Results", "order": [2], "page": 3},
        "p4": {"text": "Secondary outcomes aligned with expectations.", "order": [3], "page": 3},
        "p5": {"text": "Discussion", "order": [4], "page": 4},
        "p6": {"text": "These findings support adoption.", "order": [5], "page": 4},
    }

    document = ArticleDocument(
        source_file="duplicate.pdf",
        doc_type="article",
        doc_subtype="research",
        title="Duplicate Heading",
        sections={},
    )
    context = SecondPassContext(
        validation_issues=[ValidationIssue("Research article has too few sections")],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={"sectionizer": {"min_sections_research": 2}},
        mode="always",
        doc_metrics={"sections_count": 0},
        max_runtime_ms=2500,
    )

    result = apply_sectionizer_salvage(document, context)

    assert result.applied is True
    assert len(document.sections) == 2
    combined_text = "\n".join(document.sections.values())
    assert "Primary outcome" in combined_text
    assert "Secondary outcomes" in combined_text


def test_sectionizer_salvage_drops_caption_heavy_sections() -> None:
    paragraph_store = {
        "p1": {"text": "Results", "order": [0], "page": 2},
        "p2": {
            "text": "Figure 1. Patient flow diagram. Figure 2. Lesion sampling map. [1] [2] [3]",
            "order": [1],
            "page": 2,
        },
        "p3": {"text": "Discussion", "order": [2], "page": 3},
        "p4": {"text": "Interpretation of the diagnostic performance is provided.", "order": [3], "page": 3},
    }

    document = ArticleDocument(
        source_file="captions.pdf",
        doc_type="article",
        doc_subtype="research",
        title="Caption Heavy",
        sections={},
    )
    context = SecondPassContext(
        validation_issues=[ValidationIssue("Research article has too few sections")],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={"sectionizer": {"min_sections_research": 2}},
        mode="always",
        doc_metrics={"sections_count": 0},
        max_runtime_ms=2500,
    )

    result = apply_sectionizer_salvage(document, context)

    assert result.applied is True
    assert "results" not in document.sections
    assert "discussion" in document.sections


def test_sectionizer_salvage_marks_editorial_mode_and_counts() -> None:
    paragraph_store = {
        "p1": {"text": "Introduction", "order": [0], "page": 1},
        "p2": {"text": "Intro content.", "order": [1], "page": 1},
        "p3": {"text": "Discussion", "order": [2], "page": 2},
        "p4": {"text": "Editorial perspective on workflow.", "order": [3], "page": 2},
    }

    document = ArticleDocument(
        source_file="editorial.pdf",
        doc_type="article",
        doc_subtype="editorial_or_economics",
        title="Editorial salvage",
        sections={},
    )
    document.pipeline_info["second_pass"] = {}
    context = SecondPassContext(
        validation_issues=[ValidationIssue("Research article has too few sections")],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile="enriched",
        engines_tried=["pymupdf"],
        emit_policies={},
        config={"sectionizer": {"min_sections_research": 2}},
        mode="always",
        doc_metrics={"sections_count": 0},
        max_runtime_ms=2500,
    )

    result = apply_sectionizer_salvage(document, context)

    assert result.applied is True
    pipeline_info = document.pipeline_info
    assert pipeline_info.get("sectionizer_mode") == "editorial"
    assert pipeline_info.get("sections_rebuilt") == len(document.sections)
    assert pipeline_info.get("imrad_required") is False
