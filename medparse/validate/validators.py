"""Output validation for Medparse extractors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

from medparse.schema.article import ArticleDocument
from medparse.schema.ifu import IFUDocument
from medparse.schema.textbook import TextbookChapterDocument

Severity = Literal["warning", "error"]


@dataclass
class ValidationIssue:
    message: str
    severity: Severity = "error"


def validate_document(document, *, min_safety_blocks: int = 20) -> List[ValidationIssue]:
    """Validate a document instance and return issues."""

    if isinstance(document, ArticleDocument):
        return _validate_article(document)
    if isinstance(document, IFUDocument):
        return _validate_ifu(document, min_safety_blocks=min_safety_blocks)
    if isinstance(document, TextbookChapterDocument):
        return _validate_textbook(document)
    return []


def _validate_article(document: ArticleDocument) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    summary = document.yield_summary
    if summary:
        if summary.strict_numerator is not None and summary.strict_denominator is not None:
            if summary.strict_denominator <= 0 or summary.strict_numerator < 0:
                issues.append(
                    ValidationIssue("Yield denominator must be > 0 and numerator cannot be negative.")
                )
            if summary.strict_numerator and summary.strict_numerator > summary.strict_denominator:
                issues.append(
                    ValidationIssue("Yield numerator exceeds denominator; check strict counts.")
                )
        if summary.strict_yield is not None:
            if not (0.0 <= summary.strict_yield <= 1.0):
                issues.append(
                    ValidationIssue("Strict yield must be expressed as a fraction between 0 and 1.")
                )
    return issues


def _validate_ifu(document: IFUDocument, *, min_safety_blocks: int) -> List[ValidationIssue]:
    """Validate IFU document with front-matter checks and whitespace quality.

    Front-matter validation logic:
    - For Intuitive Surgical IFUs (large, complex): missing fields are ERRORS (strict requirement)
    - For other manufacturers: missing fields are WARNINGS (different formats expected)
    """
    issues: List[ValidationIssue] = []

    # Front-matter fields - strict validation for Intuitive Surgical IFUs only
    # Other manufacturers may use different front-matter formats
    is_intuitive_ifu = (
        document.manufacturer
        and "Intuitive Surgical" in document.manufacturer
    )
    fm_severity: Severity = "error" if is_intuitive_ifu else "warning"

    required = ("part_number", "revision", "publication_date", "model")
    for field in required:
        value = getattr(document, field)
        if not value:
            issues.append(
                ValidationIssue(
                    f"IFU missing front-matter field '{field}'.",
                    severity=fm_severity
                )
            )

    # Manufacturer and product name should be present (warnings if missing)
    if not document.manufacturer:
        issues.append(
            ValidationIssue("IFU missing manufacturer field.", severity="warning")
        )
    if not document.product_name:
        issues.append(
            ValidationIssue("IFU missing product_name field.", severity="warning")
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
        issues.append(
            ValidationIssue("No sections parsed for textbook chapter; ingestion likely failed.")
        )
    return issues


__all__ = ["ValidationIssue", "validate_document"]
