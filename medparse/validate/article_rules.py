"""Article-specific validation rules aligned with enrichment thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Sequence

from medparse.config import ExtractionConfig, FrozenNamespace
from medparse.schema.article import ArticleDocument, GuidelineRecommendation

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
    statement_cfg = getattr(thresholds, "statement", FrozenNamespace())
    classification_cfg = getattr(thresholds, "classification", FrozenNamespace())
    research_cfg = getattr(thresholds, "research", FrozenNamespace())

    if doc.doc_subtype == "guideline":
        min_recs = _coerce_int(getattr(guideline_cfg, "min_recommendations", 8))
        min_sections = _coerce_int(getattr(guideline_cfg, "min_sections", 1))
        grade_density_cfg = getattr(guideline_cfg, "grade_density", None)
        if grade_density_cfg is None:
            grade_density_cfg = getattr(guideline_cfg, "min_grade_density", 0.7)
        min_grade_density = float(grade_density_cfg)

        author_count = len(doc.authors or [])
        if author_count == 0:
            issues.append(Issue.warn("Guideline authors missing or not detected."))
        elif author_count < 3:
            issues.append(Issue.warn(f"Guideline extracted with few authors ({author_count})."))

        title_conf = float(doc.title_confidence or 0.0)
        if not doc.title:
            issues.append(Issue.warn("Guideline title missing."))
        elif title_conf < 0.6:
            issues.append(Issue.warn(f"Guideline title confidence low ({title_conf:.2f})."))

        graded_count, rec_count, grade_ratio = _grade_density_stats(doc.recommendations or [])
        if min_sections and not sections_ok(doc, min_sections=min_sections):
            issues.append(
                Issue.error(
                    f"Guideline has too few populated sections: {len(doc.sections or {})}/{min_sections}"
                )
            )

        if rec_count < max(1, min_recs):
            issues.append(
                Issue.error(
                    f"Guideline has too few recommendations: {rec_count}/{min_recs}"
                )
            )
        else:
            if grade_ratio < max(0.0, min_grade_density):
                issues.append(
                    Issue.error("Guideline grade density below 70%")
                )

        return issues

    if doc.doc_subtype in {"statement", "classification"}:
        min_sections_statement = _coerce_int(getattr(statement_cfg, "min_sections", 1))
        min_sections_classification = _coerce_int(getattr(classification_cfg, "min_sections", 1))
        min_sections_required = min_sections_statement if doc.doc_subtype == "statement" else min_sections_classification

        signals = _statement_support_signals(doc, min_sections=max(1, min_sections_required))

        if doc.doc_subtype == "statement":
            require_defs = bool(getattr(statement_cfg, "require_yield_definitions", False))
            if require_defs and not bool(doc.yield_definitions_present):
                issues.append(Issue.error("Statement gating failed: yield_definitions_missing"))
        if signals == 0:
            label = "Statement" if doc.doc_subtype == "statement" else "Classification"
            issues.append(Issue.error(f"{label} gating failed: insufficient structural signals"))

        return issues

    if doc.doc_subtype == "review":
        min_sections = _coerce_int(getattr(research_cfg, "min_sections", 4))
        if min_sections and not sections_ok(doc, min_sections=min_sections):
            issues.append(Issue.warn(f"Review article has too few sections: {len(doc.sections or {})}/{min_sections}"))
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


def _grade_density_stats(
    recommendations: Sequence[GuidelineRecommendation],
) -> tuple[int, int, float]:
    total = len(recommendations)
    if total == 0:
        return 0, 0, 0.0
    graded = sum(
        1
        for rec in recommendations
        if rec.grade or rec.statement_type in {"ungraded", "consensus", "good_practice"}
    )
    ratio = graded / total if total else 0.0
    return graded, total, ratio


def _statement_support_signals(doc: ArticleDocument, min_sections: int) -> int:
    signals = 0
    if bool(getattr(doc, "yield_definitions_present", False)):
        signals += 1
    if sections_ok(doc, min_sections=min_sections):
        signals += 1
    if _has_definition_table(doc):
        signals += 1
    return signals


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

    # If marked as non-ATS-compliant with reasons, capture warning context
    if not compatible and exclusion_reasons:
        if any(
            "numerator/denominator not reported" in str(reason).lower()
            for reason in exclusion_reasons
        ):
            issues.append(
                Issue.warn(
                    "Diagnostic yield percentage present but numerator/denominator not reported at attempted/performed level"
                )
            )
        return issues

    # ATS-compliant yields MUST have numerator and denominator
    if strict_flag or compatible:
        if numerator is None or denominator is None:
            details = f"value={value}, numerator={numerator}, denominator={denominator}"
            issues.append(Issue.error(f"ATS-compliant yield requires numerator/denominator: {details}"))
    else:
        if numerator is None or denominator is None:
            if value is not None:
                # Has a percentage but no n/d - this is acceptable with warning
                issues.append(
                    Issue.warn(
                        "Diagnostic yield percentage present but numerator/denominator not reported at attempted/performed level"
                    )
                )

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


def _has_definition_table(doc: ArticleDocument) -> bool:
    tables = getattr(doc, "tables", []) or []
    for table in tables:
        caption = getattr(table, "caption", "") or ""
        label = getattr(table, "label", "") or ""
        table_type = getattr(table, "table_type", "") or ""
        combined = f"{caption} {label} {table_type}".lower()
        if "definition" in combined or "definitions" in combined:
            return True
    return False


__all__ = ["Issue", "sections_ok", "validate_article"]
