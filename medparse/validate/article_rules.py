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
        min_recs = _coerce_int(getattr(guideline_cfg, "min_recommendations", 0))
        min_sections = _coerce_int(getattr(guideline_cfg, "min_sections", 0))

        if _meets_guideline_requirements(doc, min_recs=min_recs, min_sections=min_sections):
            return issues
        issues.append(Issue.error("Guideline gating failed: not enough recommendations/sections"))
        return issues

    # Treat everything else as research-style validation
    min_sections = _coerce_int(getattr(research_cfg, "min_sections", 0))
    if min_sections and not sections_ok(doc, min_sections=min_sections):
        issues.append(Issue.error("Too few sections"))

    require_diagnostic_yield = bool(getattr(research_cfg, "require_diagnostic_yield", False))
    if require_diagnostic_yield:
        issues.extend(_check_diagnostic_yield(doc))

    return issues


def sections_ok(doc: ArticleDocument, *, min_sections: int) -> bool:
    if min_sections <= 0:
        return True
    section_texts = (doc.sections or {}).values()
    non_empty = sum(1 for text in section_texts if isinstance(text, str) and text.strip())
    return non_empty >= min_sections


def _meets_guideline_requirements(doc: ArticleDocument, *, min_recs: int, min_sections: int) -> bool:
    rec_count = len(doc.recommendations or [])
    if rec_count < max(min_recs, 0):
        return False
    if min_sections and not sections_ok(doc, min_sections=min_sections):
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
    strict_flag = _resolve_strict_flag(diagnostic_yield)

    if strict_flag:
        if numerator is None or denominator is None:
            issues.append(Issue.error("Diagnostic yield present but numerator/denominator missing"))
    else:
        if numerator is None or denominator is None:
            issues.append(Issue.warn("Relaxed diagnostic yield lacks numerator/denominator"))

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
