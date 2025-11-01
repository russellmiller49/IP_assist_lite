"""ATS-compliant diagnostic yield extraction and validation."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from medparse.normalize.tables_classifier import TableBlock

RE_N = re.compile(r"(?:n\s*=\s*)?(\d{2,5})\s+(patients?|lesions?|nodules?)", re.IGNORECASE)
RE_YIELD = re.compile(
    r"diagnostic\s+yield\s+was\s+(?:~|about\s+)?(\d{1,3}(?:\.\d+)?)\s?%",
    re.IGNORECASE,
)
RE_PATIENTS = re.compile(
    r"(\d{2,5})(?:\s+[A-Za-z/\-]+){0,3}\s+(?:patients?|subjects?)",
    re.IGNORECASE,
)
RE_LESIONS = re.compile(
    r"(\d{2,5})(?:\s+[A-Za-z/\-]+){0,3}\s+(?:lesions?|nodules?)",
    re.IGNORECASE,
)

ATS_REASON_NO_N_OVER_N = "no_n_over_N"
ATS_REASON_FOLLOW_UP = "follow_up_used_in_numerator"
ATS_REASON_NONSPECIFIC = "nonspecific_counts_included"
ATS_REASON_DERIVED = "derived_counts_from_percent"


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
    denominator_hint: Optional[str] = None
    lesion_denominator: Optional[int] = None
    patient_denominator: Optional[int] = None


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
    patterns: List[Tuple[str, re.Pattern[str]]] = [
        (
            "pct_with_fraction",
            re.compile(r'(\d+(?:\.\d+)?)\s?%[^\n]*?\((\d+)\s*/\s*(\d+)\)', re.IGNORECASE),
        ),
        (
            "fraction",
            re.compile(r'diagnostic\s+yield[:\s]+(\d+)/(\d+)\s*', re.IGNORECASE),
        ),
        (
            "x_of_y",
            re.compile(
                r'(\d+)\s+of\s+(\d+)\s+(?:patients?|procedures?)\s+(?:had|received|achieved)\s+(?:a\s+)?(?:definitive\s+)?diagnos',
                re.IGNORECASE,
            ),
        ),
    ]

    for pattern_type, regex in patterns:
        match = regex.search(results_text)
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

    yield_match = RE_YIELD.search(results_text)
    if yield_match:
        yield_pct = float(yield_match.group(1))
        exclusion_reasons = [ATS_REASON_NO_N_OVER_N]
        match_start, match_end = yield_match.start(), yield_match.end()
        ci_lower, ci_upper = extract_confidence_intervals(results_text, match_start, match_end)
        definition = extract_yield_definition(results_text, match_start, match_end)
        context_window = _yield_context(results_text, match_start, match_end)
        numerator, denominator_from_context, denom_label, lesion_count, patient_count = _infer_counts_from_context(
            yield_pct,
            context_window,
        )
        denominator_hint = None
        if denominator_from_context and denom_label:
            denominator_hint = f"{denominator_from_context} {denom_label}"
            exclusion_reasons.append(ATS_REASON_DERIVED)

        return DiagnosticYieldATS(
            numerator=numerator,
            denominator=denominator_from_context,
            yield_pct=yield_pct,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            definition=definition,
            compatible_with_ats=False,
            exclusion_reasons=exclusion_reasons,
            evidence=EvidenceSpan(text=yield_match.group(0), confidence=0.6),
            strict=False,
            denominator_hint=denominator_hint,
            lesion_denominator=lesion_count,
            patient_denominator=patient_count,
        )

    return None


def _yield_context(text: str, start: int, end: int, window: int = 300) -> str:
    return text[max(0, start - window):min(len(text), end + window)]


def _infer_counts_from_context(
    yield_pct: float,
    context: str,
) -> tuple[Optional[int], Optional[int], Optional[str], Optional[int], Optional[int]]:
    lesion_count = None
    patient_count = None
    for match in RE_LESIONS.finditer(context):
        try:
            lesion_count = int(match.group(1))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
    for match in RE_PATIENTS.finditer(context):
        try:
            patient_count = int(match.group(1))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue

    denominator = None
    label = None
    if lesion_count:
        denominator = lesion_count
        label = "lesions"
    elif patient_count:
        denominator = patient_count
        label = "patients"

    numerator = None
    if denominator is not None:
        numerator = int(round((yield_pct / 100.0) * denominator))

    return numerator, denominator, label, lesion_count, patient_count


def _populate_denominator_from_sections(
    yield_data: DiagnosticYieldATS,
    sections: Dict[str, str],
) -> None:
    if yield_data.denominator_hint and yield_data.lesion_denominator:
        return
    lesion_candidate, patient_candidate = _scan_sections_for_counts(sections)
    if lesion_candidate:
        yield_data.lesion_denominator = lesion_candidate
        if not yield_data.denominator_hint:
            yield_data.denominator_hint = f"{lesion_candidate} lesions"
        if yield_data.denominator != lesion_candidate:
            yield_data.denominator = lesion_candidate
        if yield_data.yield_pct is not None:
            yield_data.numerator = int(round((yield_data.yield_pct / 100.0) * lesion_candidate))
        if ATS_REASON_DERIVED not in yield_data.exclusion_reasons:
            yield_data.exclusion_reasons.append(ATS_REASON_DERIVED)
        return
    if patient_candidate:
        yield_data.patient_denominator = patient_candidate
        if not yield_data.denominator_hint:
            yield_data.denominator_hint = f"{patient_candidate} patients"
        if yield_data.denominator is None:
            yield_data.denominator = patient_candidate
        if yield_data.numerator is None and yield_data.yield_pct is not None:
            yield_data.numerator = int(round((yield_data.yield_pct / 100.0) * patient_candidate))
        if ATS_REASON_DERIVED not in yield_data.exclusion_reasons:
            yield_data.exclusion_reasons.append(ATS_REASON_DERIVED)


def _scan_sections_for_counts(sections: Dict[str, str]) -> tuple[Optional[int], Optional[int]]:
    preferred_keys = {"abstract", "introduction", "background", "methods", "results"}
    segments: List[str] = []
    for key, value in sections.items():
        if not isinstance(value, str):
            continue
        if key and key.lower() in preferred_keys:
            segments.append(value)
    if not segments:
        segments = [value for value in sections.values() if isinstance(value, str)]

    combined = " ".join(segments)
    lesion_candidate = None
    patient_candidate = None
    for match in RE_LESIONS.finditer(combined):
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
        if value > 1500:
            continue
        lesion_candidate = value if lesion_candidate is None else max(lesion_candidate, value)
    for match in RE_PATIENTS.finditer(combined):
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
        if value > 1500:
            continue
        patient_candidate = value if patient_candidate is None else max(patient_candidate, value)
    return lesion_candidate, patient_candidate


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
    _populate_denominator_from_sections(yield_data, sections)

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
    if yield_data.numerator is None or yield_data.denominator is None:
        _append_reason(yield_data, ATS_REASON_NO_N_OVER_N)
        if yield_data.yield_pct is not None:
            _append_reason(yield_data, ATS_REASON_DERIVED)
        yield_data.compatible_with_ats = False

    # Update strict flag
    derived_counts = ATS_REASON_DERIVED in yield_data.exclusion_reasons
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
            _append_reason(yield_data, ATS_REASON_DERIVED)


def _find_cohort_size(text: str) -> Optional[int]:
    match = re.search(r'\bn\s*=\s*(\d+)', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = RE_N.search(text)
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
    exclusions: List[str] = []

    def _append(reason: str) -> None:
        if reason not in exclusions:
            exclusions.append(reason)

    lower_results = results_text.lower()

    # Check 1: Denominator excludes non-diagnostic?
    if re.search(r'exclud(?:ing|ed)\s+non-diagnostic', lower_results, re.IGNORECASE):
        _append(ATS_REASON_NONSPECIFIC)

    # Check 2: Per-lesion only (no per-patient)?
    if "per-lesion" in lower_results and "per-patient" not in lower_results:
        _append(ATS_REASON_NONSPECIFIC)

    # Check 3: Technical success conflated with diagnostic yield
    if "technical success" in lower_results and "diagnostic yield" not in lower_results:
        _append(ATS_REASON_NONSPECIFIC)

    # Check 4: Follow-up required for diagnosis?
    followup_pattern = re.compile(r'follow[-\s]*up.*(?:required|necessary|used).*diagnos', re.IGNORECASE)
    if followup_pattern.search(methods_text):
        _append(ATS_REASON_FOLLOW_UP)

    # Check 5: Index procedure vs composite endpoint
    if "composite" in lower_results or "combined" in lower_results:
        _append(ATS_REASON_NONSPECIFIC)

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
