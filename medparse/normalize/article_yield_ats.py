"""ATS-compliant diagnostic yield extraction and validation."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from medparse.normalize.tables_classifier import TableBlock


class EvidenceSpan(BaseModel):
    """Evidence location for extracted data."""

    text: str
    page: Optional[int] = None
    confidence: float = 0.8


class DiagnosticYieldATS(BaseModel):
    """Strict diagnostic yield following ATS guidelines."""
    numerator: Optional[int] = None
    denominator: Optional[int] = None
    yield_pct: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    definition: Optional[str] = None
    compatible_with_ats: bool = False
    exclusion_reasons: List[str] = Field(default_factory=list)
    evidence: Optional[EvidenceSpan] = None
    strict: bool = True


def extract_ats_compliant_yield(
    sections: Dict[str, str],
    tables: List[TableBlock]
) -> Optional[DiagnosticYieldATS]:
    """Extract diagnostic yield following ATS guidelines.

    ATS-compliant yield must be:
    - Per procedural encounter (not per-lesion only)
    - Definitive diagnosis at index procedure
    - Clear denominator provenance
    - Includes non-diagnostic cases in denominator

    Args:
        sections: Document sections
        tables: Classified tables

    Returns:
        DiagnosticYieldATS object or None
    """
    results_text = sections.get('results', '') or ''
    methods_text = sections.get('methods', '') or ''

    table_candidate = _extract_from_tables(tables)
    if table_candidate:
        _finalize_yield_record(table_candidate, results_text, methods_text, sections)
        return table_candidate

    text_candidate = _extract_from_text(results_text)
    if text_candidate:
        _finalize_yield_record(text_candidate, results_text, methods_text, sections)
        return text_candidate

    return None


def _extract_from_tables(tables: List[TableBlock]) -> Optional[DiagnosticYieldATS]:
    for table in tables:
        if table.table_type not in {'diagnostic_yield', 'diagnostic_accuracy'}:
            continue
        candidate = _extract_yield_from_table(table)
        if candidate:
            return candidate
    return None


def _extract_from_text(results_text: str) -> Optional[DiagnosticYieldATS]:
    if not results_text:
        return None

    # Try patterns in order of specificity (most specific first)
    patterns = [
        (r'(\d+(?:\.\d+)?)\s?%[^\n]*?\((\d+)\s*/\s*(\d+)\)', 'pct_with_fraction'),
        (r'diagnostic\s+yield[:\s]+(\d+)/(\d+)\s*', 'fraction'),
        (r'(\d+)\s+of\s+(\d+)\s+(?:patients?|procedures?)\s+(?:had|received|achieved)\s+(?:a\s+)?(?:definitive\s+)?diagnos', 'x_of_y'),
        (r'diagnostic\s+yield(?:\s+was|\s*[:=])\s*(\d+(?:\.\d+)?)\s?%', 'pct_only'),
    ]

    for pattern_str, pattern_type in patterns:
        match = re.search(pattern_str, results_text, re.IGNORECASE)
        if not match:
            continue

        groups = match.groups()
        numerator = denominator = None
        yield_pct = None
        exclusion_reasons = []

        if pattern_type == 'pct_with_fraction':
            # Has percentage and explicit numerator/denominator
            yield_pct = float(groups[0])
            numerator = int(groups[1])
            denominator = int(groups[2])
        elif pattern_type == 'fraction':
            # Has explicit fraction
            numerator = int(groups[0])
            denominator = int(groups[1])
            yield_pct = (numerator / denominator) * 100 if denominator > 0 else None
        elif pattern_type == 'x_of_y':
            # X of Y pattern
            numerator = int(groups[0])
            denominator = int(groups[1])
            yield_pct = (numerator / denominator) * 100 if denominator > 0 else None
        elif pattern_type == 'pct_only':
            # Only percentage, no numerator/denominator
            yield_pct = float(groups[0])
            exclusion_reasons.append("numerator/denominator not reported at attempted/performed level")

        match_start, match_end = match.start(), match.end()
        ci_lower, ci_upper = extract_confidence_intervals(results_text, match_start, match_end)
        definition = extract_yield_definition(results_text, match_start, match_end)

        # Determine ATS compliance based on whether we have n/d
        compatible = (numerator is not None and denominator is not None)
        strict = compatible and pattern_type != 'pct_only'

        return DiagnosticYieldATS(
            numerator=numerator,
            denominator=denominator,
            yield_pct=yield_pct,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            definition=definition,
            compatible_with_ats=compatible,
            exclusion_reasons=exclusion_reasons,
            evidence=EvidenceSpan(text=match.group(0), confidence=0.85 if compatible else 0.6),
            strict=strict,
        )

    return None


def _extract_yield_from_table(table: TableBlock) -> Optional[DiagnosticYieldATS]:
    headers = [header.lower() for header in table.headers]
    target_indices = [idx for idx, header in enumerate(headers) if any(token in header for token in ('diagnostic yield', 'yield', '%'))]
    if not target_indices:
        return None

    for row in table.rows:
        for idx in target_indices:
            if idx >= len(row):
                continue
            cell_value = row[idx]
            if not isinstance(cell_value, str):
                continue

            fraction_match = re.search(r'(\d+)\s*/\s*(\d+)', cell_value)
            pct_match = re.search(r'([\d.]+)\s?%', cell_value)

            numerator = int(fraction_match.group(1)) if fraction_match else None
            denominator = int(fraction_match.group(2)) if fraction_match else None
            yield_pct = float(pct_match.group(1)) if pct_match else None

            if numerator is None and denominator is None and yield_pct is None:
                continue

            return DiagnosticYieldATS(
                numerator=numerator,
                denominator=denominator,
                yield_pct=yield_pct,
                definition=f"From table: {table.caption or 'Diagnostic Yield'}",
                evidence=EvidenceSpan(
                    text=cell_value,
                    page=table.page,
                    confidence=0.85 if fraction_match else 0.7,
                ),
            )
    return None


def _finalize_yield_record(
    yield_data: DiagnosticYieldATS,
    results_text: str,
    methods_text: str,
    sections: Dict[str, str],
) -> None:
    # Try to backfill missing counts from text
    _attempt_backfill_counts(yield_data, sections)

    # Check ATS compliance criteria
    compat, exclusions = validate_ats_compliance(results_text, methods_text)

    # If we already marked it as non-compliant due to missing n/d, keep that
    if not yield_data.compatible_with_ats:
        # Already marked as non-compliant, just add more reasons if found
        for reason in exclusions:
            _append_reason(yield_data, reason)
    else:
        # Was marked as compliant, update based on validation
        yield_data.compatible_with_ats = compat
        for reason in exclusions:
            _append_reason(yield_data, reason)

    # Add missing data reasons
    baseline_reason = "numerator/denominator not reported at attempted/performed level"
    if yield_data.numerator is None or yield_data.denominator is None:
        _append_reason(yield_data, baseline_reason)

    # Update strict flag
    derived_counts = "derived_counts_from_percent" in yield_data.exclusion_reasons
    yield_data.strict = (
        yield_data.numerator is not None
        and yield_data.denominator is not None
        and not derived_counts
        and yield_data.compatible_with_ats
    )


def _attempt_backfill_counts(yield_data: DiagnosticYieldATS, sections: Dict[str, str]) -> None:
    if yield_data.numerator is not None and yield_data.denominator is not None:
        return

    combined_text = " \n".join(value for value in sections.values() if isinstance(value, str))
    if not combined_text:
        return

    pct_fraction = re.search(r'(\d+(?:\.\d+)?)\s?%[^\n]*?\((\d+)\s*/\s*(\d+)\)', combined_text, re.IGNORECASE)
    if pct_fraction:
        if yield_data.yield_pct is None:
            yield_data.yield_pct = float(pct_fraction.group(1))
        if yield_data.numerator is None:
            yield_data.numerator = int(pct_fraction.group(2))
        if yield_data.denominator is None:
            yield_data.denominator = int(pct_fraction.group(3))
        return

    if yield_data.yield_pct is not None:
        denominator = _find_cohort_size(combined_text)
        if denominator and yield_data.denominator is None:
            yield_data.denominator = denominator
        if denominator and yield_data.numerator is None:
            yield_data.numerator = int(round((yield_data.yield_pct / 100.0) * denominator))
            _append_reason(yield_data, "derived_counts_from_percent")


def _find_cohort_size(text: str) -> Optional[int]:
    match = re.search(r'\bn\s*=\s*(\d+)', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r'(\d+)\s+(?:patients|subjects|cases|procedures)\b', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _append_reason(yield_data: DiagnosticYieldATS, reason: str) -> None:
    if reason and reason not in yield_data.exclusion_reasons:
        yield_data.exclusion_reasons.append(reason)


def validate_ats_compliance(results_text: str, methods_text: str) -> Tuple[bool, List[str]]:
    """Check if yield meets ATS strict criteria.

    Args:
        results_text: Results section text
        methods_text: Methods section text

    Returns:
        Tuple of (is_compatible, list_of_exclusion_reasons)
    """
    exclusions = []

    # Check 1: Denominator excludes non-diagnostic?
    if re.search(r'exclud(?:ing|ed)\s+non-diagnostic', results_text, re.IGNORECASE):
        exclusions.append("Denominator excludes non-diagnostic cases (should include)")

    # Check 2: Per-lesion only (no per-patient)?
    if 'per-lesion' in results_text.lower() and 'per-patient' not in results_text.lower():
        exclusions.append("Only per-lesion yield reported (need per-patient)")

    # Check 3: Technical success conflated with diagnostic yield
    if 'technical success' in results_text.lower():
        # Check if diagnostic yield is also mentioned
        if 'diagnostic yield' not in results_text.lower():
            exclusions.append("Only technical success reported (not diagnostic yield)")

    # Check 4: Follow-up required for diagnosis?
    if re.search(r'follow-up.*(?:required|necessary|used).*diagnosis', methods_text, re.IGNORECASE):
        # Check if follow-up period is adequate (≥6 months)
        followup_match = re.search(r'(\d+)\s*(?:day|week|month|year).*follow-up', methods_text, re.IGNORECASE)
        if followup_match:
            value = int(followup_match.group(1))
            unit = re.search(r'(day|week|month|year)', followup_match.group(0), re.IGNORECASE).group(1).lower()

            # Convert to months
            months = value
            if unit == 'day':
                months = value / 30
            elif unit == 'week':
                months = value / 4
            elif unit == 'year':
                months = value * 12

            if months < 6:
                exclusions.append(f"Follow-up period inadequate ({value} {unit}, need ≥6 months)")
        else:
            exclusions.append("Follow-up period not specified")

    # Check 5: Index procedure vs composite endpoint
    if 'composite' in results_text.lower() or 'combined' in results_text.lower():
        exclusions.append("Composite endpoint used (not index procedure alone)")

    return (len(exclusions) == 0), exclusions


def extract_yield_definition(text: str, start: int, end: int, window: int = 200) -> str:
    """Extract surrounding context for yield definition.

    Args:
        text: Full text
        start: Match start position
        end: Match end position
        window: Characters before/after to include

    Returns:
        Context string
    """
    return text[max(0, start-window):min(len(text), end+window)].strip()


def extract_confidence_intervals(text: str, start: int, end: int, window: int = 100) -> Tuple[Optional[float], Optional[float]]:
    """Extract 95% CI from vicinity of yield statement.

    Args:
        text: Full text
        start: Match start position
        end: Match end position
        window: Characters to search

    Returns:
        Tuple of (ci_lower, ci_upper) or (None, None)
    """
    vicinity = text[max(0, start):min(len(text), end+window)]

    # Pattern: 95% CI: 75-85% or (CI 75-85%)
    ci_pattern = r'(?:95%\s*)?(?:CI|confidence interval)[:\s]+\(?(\d+(?:\.\d+)?)[%-]*\s*[-–]\s*(\d+(?:\.\d+)?)[%\)]?'
    match = re.search(ci_pattern, vicinity, re.IGNORECASE)

    if match:
        try:
            ci_lower = float(match.group(1))
            ci_upper = float(match.group(2))
            return (ci_lower, ci_upper)
        except ValueError:
            pass

    return (None, None)


__all__ = [
    "extract_ats_compliant_yield",
    "DiagnosticYieldATS",
    "validate_ats_compliance",
]
