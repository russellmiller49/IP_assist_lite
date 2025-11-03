"""Output validation for Medparse extractors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

from medparse.config import ExtractionConfig, get_extraction_config
from medparse.schema.article import ArticleDocument
from medparse.schema.ifu import IFUDocument
from medparse.schema.textbook import TextbookChapterDocument
from medparse.validate.article_rules import Issue as ArticleIssue
from medparse.validate.article_rules import validate_article as run_article_rules
from medparse.validate.ifu_rules import Issue as IfuIssue
from medparse.validate.ifu_rules import validate_ifu as run_ifu_rules

Severity = Literal["warning", "error"]


@dataclass
class ValidationIssue:
    message: str
    severity: Severity = "error"


def validate_document(document, *, min_safety_blocks: int = 20) -> List[ValidationIssue]:
    """Validate a document instance and return issues."""

    config = get_extraction_config()
    if isinstance(document, ArticleDocument):
        return _validate_article(document, config)
    if isinstance(document, IFUDocument):
        return _validate_ifu(document, config, min_safety_blocks=min_safety_blocks)
    if isinstance(document, TextbookChapterDocument):
        return _validate_textbook(document)
    return []


def _validate_article(document: ArticleDocument, config: ExtractionConfig) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not document.title:
        issues.append(ValidationIssue("Article missing title after normalization."))
    elif document.title.isupper() and len(document.title.split()) <= 6:
        issues.append(ValidationIssue("Article title appears to be an ALL-CAPS organization name."))

    if not document.sections:
        issues.append(ValidationIssue("No sections parsed for article; enrichment likely failed."))

    if document.recommendations:
        graded = sum(
            1
            for rec in document.recommendations
            if rec.grade or rec.statement_type in {"ungraded", "good_practice", "consensus"}
        )
        ratio = graded / len(document.recommendations)
        if ratio < 0.7:
            issues.append(
                ValidationIssue(
                    "Guideline recommendations missing grade/ungraded tag for >=30% of entries.",
                )
            )

    article_issues = run_article_rules(document, config)
    for issue in article_issues:
        issues.append(ValidationIssue(issue.message, severity=issue.severity))
    return issues


def _validate_ifu(
    document: IFUDocument,
    config: ExtractionConfig,
    *,
    min_safety_blocks: int,
) -> List[ValidationIssue]:
    """Validate IFU document with front-matter checks and whitespace quality.

    Front-matter validation logic:
    - For Intuitive Surgical IFUs (large, complex): missing fields are ERRORS (strict requirement)
    - For other manufacturers: missing fields are WARNINGS (different formats expected)
    """
    issues: List[ValidationIssue] = []

    rule_issues = run_ifu_rules(document, config)
    for issue in rule_issues:
        issues.append(ValidationIssue(issue.message, severity=issue.severity))

    # Manufacturer and product name should be present (warnings if missing)
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    front_meta = pipeline_info.get("front_matter_meta", {}) if isinstance(pipeline_info, dict) else {}

    if not document.manufacturer:
        issues.append(
            ValidationIssue("IFU missing manufacturer field.", severity="warning")
        )
    if not document.product_name:
        product_severity = "error"
        if document.manufacturer and isinstance(front_meta, dict) and front_meta.get("product_name_source") == "metadata_title":
            product_severity = "warning"
        issues.append(
            ValidationIssue("IFU missing product_name field.", severity=product_severity)
        )

    # Whitespace quality check: look for run-together tokens in clinical fields
    whitespace_fields = [
        ("indications_for_use", document.indications_for_use),
        ("intended_use", document.intended_use),
        ("intended_user", document.intended_user),
    ]
    for field_name, field_value in whitespace_fields:
        if field_value and isinstance(field_value, str):
            # Check for run-together patterns like "TheIon" or capital letter fusions
            if _has_whitespace_issues(field_value):
                issues.append(
                    ValidationIssue(
                        f"Field '{field_name}' contains run-together tokens (whitespace restoration failed)."
                    )
                )

    # Safety blocks check
    if len(document.safety_blocks) < min_safety_blocks:
        issues.append(
            ValidationIssue(
                f"Expected at least {min_safety_blocks} safety blocks; found {len(document.safety_blocks)}.",
                severity="warning",
            )
        )

    # References should be empty for IFU unless true bibliography detected
    if document.references:
        issues.append(
            ValidationIssue(
                "References detected for IFU – ensure a proper References/Bibliography anchor exists.",
                severity="warning",
            )
        )

    return issues


def _has_whitespace_issues(text: str) -> bool:
    """Detect run-together tokens indicating whitespace restoration failure."""
    import re

    # Patterns indicating missing spaces:
    # 1. CamelCase fusions like "TheIon" or "SystemInstruments"
    # 2. Number-letter fusions like "System3" (legitimate) vs "3System" (suspicious)
    suspicious_patterns = [
        r'\b[A-Z][a-z]+[A-Z][a-z]+[A-Z]',  # e.g., "TheIonSystem"
        r'\b\d+[A-Z][a-z]+',  # e.g., "3System" (suspicious)
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, text):
            return True

    return False


def _validate_textbook(document: TextbookChapterDocument) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not document.book_meta:
        issues.append(
            ValidationIssue(
                "Missing book metadata for textbook chapter.", severity="warning"
            )
        )
    if not document.sections:
        # Check if there's other meaningful content before marking as hard error
        has_content = (
            document.chapter_title
            or document.chapter_authors
            or document.keywords
            or document.figures
            or (document.page_count and document.page_count > 0)
        )
        if has_content:
            issues.append(
                ValidationIssue(
                    "No structured sections parsed; chapter may lack standard section headers.",
                    severity="warning"
                )
            )
        else:
            issues.append(
                ValidationIssue("No sections parsed for textbook chapter; ingestion likely failed.")
            )
    else:
        for key, section in document.sections.items():
            if section.end_page is not None and section.start_page is not None:
                if section.end_page < section.start_page:
                    issues.append(
                        ValidationIssue(
                            f"Section '{key}' has inverted page span (start > end).",
                        )
                    )
    coverage = getattr(document, "coverage_ratio", None)
    if coverage is None:
        issues.append(
            ValidationIssue(
                "Textbook chapter missing coverage_ratio metric.",
            )
        )
    elif coverage < 0.80:
        issues.append(
            ValidationIssue(
                f"Textbook chapter coverage ratio below 0.80 (value={coverage:.2f}).",
            )
        )
    return issues


__all__ = ["ValidationIssue", "validate_document"]
