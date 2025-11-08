from __future__ import annotations

from medparse.pipeline.run_extract import _normalize_validator_issues
from medparse.schema.article import ArticleDocument
from medparse.validate.validators import ValidationIssue


def test_editorial_min_sections_downgraded() -> None:
    document = ArticleDocument(
        doc_type="article",
        source_file="editorial.pdf",
        page_count=1,
        doc_subtype="editorial_or_economics",
    )
    issues = [ValidationIssue("Research article has too few sections: 1/4")]
    normalized = _normalize_validator_issues(document, issues)
    assert normalized[0].severity == "warning"


def test_statement_section_signal_downgraded() -> None:
    document = ArticleDocument(
        doc_type="article",
        source_file="statement.pdf",
        page_count=1,
        doc_subtype="statement",
    )
    issues = [ValidationIssue("Statement gating failed: insufficient structural signals")]
    normalized = _normalize_validator_issues(document, issues)
    assert normalized[0].severity == "warning"
