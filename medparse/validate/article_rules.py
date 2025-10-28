"""Article-specific validation rules aligned with enrichment thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional

from medparse.config import ExtractionConfig, FrozenNamespace
from medparse.schema.article import ArticleDocument

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    message: str
    severity: Severity = "error"

    @classmethod
    def error(cls, message: str) -> "Issue":
        return cls(message=message, severity="error")

    @classmethod
    def warn(cls, message: str) -> "Issue":
        return cls(message=message, severity="warning")


def validate_article(doc: ArticleDocument, cfg: ExtractionConfig) -> List[Issue]:
    """Validate article output using profile-specific thresholds."""

    issues: List[Issue] = []
    thresholds = cfg.thresholds
    guideline_cfg = getattr(thresholds, "guideline", FrozenNamespace())
    research_cfg = getattr(thresholds, "research", FrozenNamespace())

    if doc.doc_subtype == "guideline":
        min_recs = _coerce_int(getattr(guideline_cfg, "min_recommendations", 8))
        min_sections = _coerce_int(getattr(guideline_cfg, "min_sections", 1))
        min_grade_density = float(getattr(guideline_cfg, "min_grade_density", 0.7))

        if not _meets_guideline_requirements(
            doc,
            min_recs=min_recs,
            min_sections=min_sections,
            min_grade_density=min_grade_density
        ):
            recommendations = doc.recommendations or []
            rec_count = len(recommendations)
            graded_count = sum(
                1 for rec in recommendations
                if rec.grade or rec.statement_type in {"ungraded", "consensus", "good_practice"}
            )
            grade_density = graded_count / rec_count if rec_count > 0 else 0.0

            details = f"recs={rec_count}/{min_recs}, grade_density={grade_density:.1%}/{min_grade_density:.0%}"
            issues.append(Issue.error(f"Guideline requirements not met: {details}"))

        # Guidelines do NOT require diagnostic yield
        return issues

    # Research articles require different validation
    min_sections = _coerce_int(getattr(research_cfg, "min_sections", 4))
    if min_sections and not sections_ok(doc, min_sections=min_sections):
        issues.append(Issue.error(f"Research article has too few sections: {len(doc.sections or {})}/{min_sections}"))

    # Research articles require ATS-compliant diagnostic yield
    require_diagnostic_yield = bool(getattr(research_cfg, "require_diagnostic_yield", True))
    if require_diagnostic_yield:
        issues.extend(_check_diagnostic_yield(doc))

    return issues


def sections_ok(doc: ArticleDocument, *, min_sections: int) -> bool:
    if min_sections <= 0:
        return True
    section_texts = (doc.sections or {}).values()
    non_empty = sum(1 for text in section_texts if isinstance(text, str) and text.strip())
    return non_empty >= min_sections


def _meets_guideline_requirements(
    doc: ArticleDocument,
    *,
    min_recs: int,
    min_sections: int,
    min_grade_density: float = 0.7
) -> bool:
    """Check if document meets guideline requirements including grade density."""
    recommendations = doc.recommendations or []
    rec_count = len(recommendations)

    # Check minimum recommendation count
    if rec_count < max(min_recs, 0):
        return False

    # Check minimum sections
    if min_sections and not sections_ok(doc, min_sections=min_sections):
        return False

    # Check grade density (≥70% must have grade or be explicitly ungraded/consensus/good_practice)
    if rec_count > 0:
        graded_count = sum(
            1 for rec in recommendations
            if rec.grade or rec.statement_type in {"ungraded", "consensus", "good_practice"}
        )
        grade_density = graded_count / rec_count
        if grade_density < min_grade_density:
            return False

    return True


def _check_diagnostic_yield(doc: ArticleDocument) -> List[Issue]:
    issues: List[Issue] = []
    diagnostic_yield = doc.diagnostic_yield

    if diagnostic_yield is None:
        issues.append(Issue.error("Diagnostic yield missing for research article"))
        return issues

    numerator = getattr(diagnostic_yield, "numerator", None)
    denominator = getattr(diagnostic_yield, "denominator", None)
    value = getattr(diagnostic_yield, "value", None)
    compatible = getattr(diagnostic_yield, "compatible_with_ats", False)
    exclusion_reasons = getattr(diagnostic_yield, "exclusion_reasons", [])
    strict_flag = _resolve_strict_flag(diagnostic_yield)

    # If marked as non-ATS-compliant with reasons, that's acceptable
    if not compatible and exclusion_reasons:
        # This is valid - the paper reported yield but not in ATS-compliant format
        return issues

    # ATS-compliant yields MUST have numerator and denominator
    if strict_flag or compatible:
        if numerator is None or denominator is None:
            details = f"value={value}, numerator={numerator}, denominator={denominator}"
            issues.append(Issue.error(f"ATS-compliant yield requires numerator/denominator: {details}"))
    else:
        if numerator is None or denominator is None:
            if value is not None:
                # Has a percentage but no n/d - this is common and acceptable with warning
                issues.append(Issue.warn(f"Diagnostic yield {value:.1f}% lacks numerator/denominator"))

    return issues


def _resolve_strict_flag(diagnostic_yield) -> bool:
    if hasattr(diagnostic_yield, "strict") and getattr(diagnostic_yield, "strict") is not None:
        return bool(getattr(diagnostic_yield, "strict"))
    if hasattr(diagnostic_yield, "compatible_with_ats"):
        return bool(getattr(diagnostic_yield, "compatible_with_ats"))
    return True


def _coerce_int(value: Optional[object]) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


__all__ = ["Issue", "sections_ok", "validate_article"]
