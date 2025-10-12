"""Validation layer for Medparse outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from medparse.types import BaseDocument
from medparse.types.guideline import GuidelineDocument
from medparse.types.ifu import IFUDocument
from medparse.types.research import ResearchDocument


@dataclass
class ValidationIssue:
    """Represents a validation warning or error."""

    message: str
    severity: str = "warning"


KNOWN_GRADE_SCALES = {"GRADE", "SIGN", "ACCP"}


def validate_document(document: BaseDocument) -> List[ValidationIssue]:
    """Return validation issues for the supplied document."""
    issues: List[ValidationIssue] = []

    if isinstance(document, IFUDocument):
        total_admonitions = len(document.warnings) + len(document.cautions) + len(document.notes)
        if total_admonitions > 100:
            issues.append(
                ValidationIssue(
                    "IFU contains more than 100 warnings; check for duplicate parsing.", "error"
                )
            )
        if len(document.references) > 5:
            issues.append(ValidationIssue("IFU unexpectedly contains numerous references."))

    if isinstance(document, GuidelineDocument):
        for rec in document.recommendations:
            if rec.evidence is None:
                issues.append(
                    ValidationIssue(
                        f"Guideline recommendation '{rec.text[:40]}...' lacks evidence span.", "error"
                    )
                )
            if rec.strength_scale and rec.strength_scale.upper() not in KNOWN_GRADE_SCALES:
                issues.append(
                    ValidationIssue(
                        f"Unknown strength scale '{rec.strength_scale}' on recommendation {rec.number}."
                    )
                )

    if isinstance(document, ResearchDocument):
        if document.ats_yield:
            numer = document.ats_yield.numerator
            denom = document.ats_yield.denominator
            if numer < 0 or denom <= 0 or numer > denom:
                issues.append(
                    ValidationIssue("ATS yield counts invalid (numerator outside denominator).", "error")
                )
        if document.nondiagnostic:
            if document.ats_yield and document.nondiagnostic.nonspecific_inflammation:
                pass  # valid scenario; counts tracked separately

    return issues
