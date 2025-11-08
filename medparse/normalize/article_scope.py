"""Heuristics to infer the research scope for extracted articles."""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

from medparse.schema.article import ArticleDocument, EnhancedTable, ResearchOutcomeMetric

DIAGNOSTIC_PHRASES = {
    "diagnostic accuracy",
    "diagnostic yield",
    "diagnostic performance",
    "sensitivity",
    "specificity",
    "noninferiority",
    "non-inferiority",
    "pneumothorax",
}

BRONCHOSCOPY_TERMS = {
    "bronchoscopy",
    "bronchoscopic",
    "transbronchial",
    "navigational bronchoscopy",
    "robotic bronchoscopy",
    "ttnb",
    "transthoracic needle biopsy",
    "peripheral pulmonary nodule",
    "ppn",
    "peripheral lung nodule",
}

THERAPEUTIC_TERMS = {
    "endobronchial valve",
    "valve therapy",
    "lung volume reduction",
    "rheoplasty",
    "ablation",
    "stent",
    "implant",
    "treatment arm",
    "therapy arm",
}

EDITORIAL_TERMS = {
    "value-based",
    "value based",
    "practice management",
    "business plan",
    "economic analysis",
    "efficiency",
    "workflow",
    "macra",
    "mips",
    "billing",
    "coding",
}

NON_BRONCHOSCOPIC_TERMS = {
    "percutaneous endoscopic gastrostomy",
    "percutaneous radiologic gastrostomy",
    "peg tube",
    "gastrostomy tube",
    "gastrostomy",
    "peg",
    "prg",
    "interventional radiology",
    "jvir",
}

N_OVER_N_PATTERN = re.compile(r"\b\d{1,4}\s*/\s*\d{1,4}\b")


def _normalize_sections(sections: Mapping[str, str] | None) -> str:
    if not sections:
        return ""
    segments: list[str] = []
    for text in sections.values():
        if isinstance(text, str) and text.strip():
            segments.append(text.lower())
    return " ".join(segments)


def _table_text(tables: Sequence[EnhancedTable] | None) -> str:
    if not tables:
        return ""
    snippets: list[str] = []
    for table in tables:
        headers = []
        rows = []
        try:
            headers = [" ".join(row) for row in getattr(table, "headers", []) or []]
        except Exception:
            headers = []
        try:
            rows = [" ".join(row) for row in getattr(table, "rows", []) or []]
        except Exception:
            rows = []
        snippets.extend(headers)
        snippets.extend(rows)
    return " ".join(snippet.lower() for snippet in snippets if snippet)


def _research_metric_present(metric: ResearchOutcomeMetric | None) -> bool:
    if metric is None:
        return False
    if getattr(metric, "percent", None) is not None:
        return True
    if getattr(metric, "n_over_N", None) is not None:
        fraction = getattr(metric, "n_over_N")
        if getattr(fraction, "numerator", None) is not None or getattr(fraction, "denominator", None) is not None:
            return True
    if getattr(metric, "ci_95", None):
        return True
    if getattr(metric, "p_value", None) is not None:
        return True
    if getattr(metric, "evidence_ids", None):
        return True
    return False


def _has_diagnostic_metrics(document: ArticleDocument) -> bool:
    diagnostic = getattr(document, "diagnostic_yield", None)
    if diagnostic is not None:
        if getattr(diagnostic, "numerator", None) is not None or getattr(diagnostic, "denominator", None) is not None:
            return True
        if getattr(diagnostic, "value", None) is not None:
            return True
    outcomes = getattr(document, "research_outcomes", None)
    if outcomes is None:
        return False
    if _research_metric_present(getattr(outcomes, "diagnostic_accuracy", None)):
        return True
    if _research_metric_present(getattr(outcomes, "diagnostic_yield", None)):
        return True
    for arm in getattr(outcomes, "arms", []) or []:
        if _research_metric_present(getattr(arm, "diagnostic_accuracy", None)):
            return True
        if _research_metric_present(getattr(arm, "diagnostic_yield", None)):
            return True
    return False


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def infer_research_scope(document: ArticleDocument | None) -> str:
    """Classify the research scope for validator routing."""

    if not isinstance(document, ArticleDocument):
        return "unknown"

    subtype = (document.doc_subtype or "").lower()
    if subtype in {"guideline", "statement", "classification"}:
        return "unknown"
    title = (document.title or "").lower()
    abstract = (document.abstract or "").lower()
    sections_text = _normalize_sections(document.sections)
    table_text = _table_text(document.tables)
    combined = " ".join(part for part in (title, abstract, sections_text, table_text) if part)

    if subtype == "editorial_or_economics" or _contains_any(combined, EDITORIAL_TERMS):
        return "editorial_or_economics"

    if _contains_any(combined, NON_BRONCHOSCOPIC_TERMS):
        return "non_bronchoscopic"

    diag_phrase = _contains_any(combined, DIAGNOSTIC_PHRASES)
    bronchoscopy_signal = _contains_any(combined, BRONCHOSCOPY_TERMS)
    has_counts = bool(N_OVER_N_PATTERN.search(combined))
    metric_signal = _has_diagnostic_metrics(document)

    if subtype == "research_diagnostic" or (diag_phrase and (bronchoscopy_signal or has_counts or metric_signal)):
        return "diagnostic_ppn_bronchoscopy"

    if subtype == "research_therapeutic" or _contains_any(combined, THERAPEUTIC_TERMS):
        return "research_therapeutic"

    return "unknown"


__all__ = ["infer_research_scope"]
