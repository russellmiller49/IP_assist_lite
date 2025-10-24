"""ATS-compliant diagnostic yield extraction and validation."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

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
    exclusion_reasons: List[str] = []
    evidence: Optional[EvidenceSpan] = None


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
    results_text = sections.get('results', '')
    methods_text = sections.get('methods', '')

    # Pattern 1: Look for explicit yield statements in results
    yield_patterns = [
        r'diagnostic\s+yield[:\s]+(\d+)/(\d+)\s*\(?([\d.]+)%\)?',
        r'diagnosis\s+established[:\s]+(\d+)\s+of\s+(\d+)',
        r'definitive\s+(?:pathology|diagnosis)[:\s]+(\d+)/(\d+)',
        r'(\d+)\s+of\s+(\d+)\s+(?:patients?|procedures?)\s+(?:had|received|achieved)\s+(?:a\s+)?(?:definitive\s+)?diagnos',
    ]

    for pattern in yield_patterns:
        m = re.search(pattern, results_text, re.IGNORECASE)
        if m:
            numerator = int(m.group(1))
            denominator = int(m.group(2))
            yield_pct = None

            # Try to extract percentage if captured
            if m.lastindex >= 3:
                try:
                    yield_pct = float(m.group(3))
                except (ValueError, IndexError):
                    pass

            # Calculate if not provided
            if yield_pct is None and denominator > 0:
                yield_pct = (numerator / denominator) * 100

            # Extract context for definition
            match_start = m.start()
            match_end = m.end()
            definition = extract_yield_definition(results_text, match_start, match_end)

            # Validate ATS compliance
            compat, exclusions = validate_ats_compliance(results_text, methods_text)

            # Extract confidence intervals if present
            ci_lower, ci_upper = extract_confidence_intervals(results_text, match_start, match_end)

            return DiagnosticYieldATS(
                numerator=numerator,
                denominator=denominator,
                yield_pct=yield_pct,
                ci_lower=ci_lower,
                ci_upper=ci_upper,
                definition=definition,
                compatible_with_ats=compat,
                exclusion_reasons=exclusions,
                evidence=EvidenceSpan(
                    text=m.group(0),
                    confidence=0.9
                )
            )

    # Pattern 2: Look in diagnostic yield tables
    for table in tables:
        if table.table_type == 'diagnostic_yield' or table.table_type == 'diagnostic_accuracy':
            yield_data = extract_yield_from_table(table)
            if yield_data:
                # Validate ATS compliance
                compat, exclusions = validate_ats_compliance(results_text, methods_text)
                yield_data.compatible_with_ats = compat
                yield_data.exclusion_reasons = exclusions
                return yield_data

    return None


def extract_yield_from_table(table: TableBlock) -> Optional[DiagnosticYieldATS]:
    """Extract yield from table data.

    Args:
        table: Table containing yield data

    Returns:
        DiagnosticYieldATS or None
    """
    # Look for yield-related headers
    yield_headers = ['diagnostic yield', 'yield', 'diagnosis', 'n', '%', 'percentage']

    # Find yield column
    yield_col_idx = None
    for i, header in enumerate(table.headers):
        if any(yh in header.lower() for yh in yield_headers):
            yield_col_idx = i
            break

    if yield_col_idx is None:
        return None

    # Extract from first data row
    if not table.rows:
        return None

    first_row = table.rows[0]
    if yield_col_idx >= len(first_row):
        return None

    cell_value = first_row[yield_col_idx]

    # Try to parse as fraction or percentage
    fraction_match = re.search(r'(\d+)/(\d+)', cell_value)
    if fraction_match:
        numerator = int(fraction_match.group(1))
        denominator = int(fraction_match.group(2))
        yield_pct = (numerator / denominator) * 100 if denominator > 0 else None

        return DiagnosticYieldATS(
            numerator=numerator,
            denominator=denominator,
            yield_pct=yield_pct,
            definition=f"From table: {table.caption or 'Diagnostic Yield'}",
            evidence=EvidenceSpan(
                text=cell_value,
                page=table.page,
                confidence=0.85
            )
        )

    # Try percentage only
    pct_match = re.search(r'([\d.]+)%', cell_value)
    if pct_match:
        yield_pct = float(pct_match.group(1))
        return DiagnosticYieldATS(
            yield_pct=yield_pct,
            definition=f"From table: {table.caption or 'Diagnostic Yield'}",
            evidence=EvidenceSpan(
                text=cell_value,
                page=table.page,
                confidence=0.7
            )
        )

    return None


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
