"""Outcomes and harms extraction with structured fields."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from pydantic import BaseModel

from medparse.normalize.tables_classifier import TableBlock


class OutcomeData(BaseModel):
    """Structured outcome with value, confidence interval, and evidence."""
    name: str
    value: Optional[float] = None
    n: Optional[int] = None
    percent: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    denominator: Optional[int] = None
    inconclusive: bool = False
    linked_figure_table: Optional[str] = None
    evidence_text: Optional[str] = None
    page: Optional[int] = None


# Complication types to extract
COMPLICATION_TYPES = [
    'pneumothorax',
    'bleeding',
    'hemorrhage',
    'admission',
    'readmission',
    'mortality',
    'death',
    'infection',
    'respiratory failure',
    'hypoxemia',
    'desaturation',
]


def extract_outcomes(
    sections: Dict[str, str],
    tables: List[TableBlock]
) -> List[OutcomeData]:
    """Extract outcomes with n, %, CI, denominator for each complication.

    Args:
        sections: Document sections
        tables: Classified tables

    Returns:
        List of OutcomeData objects
    """
    outcomes = []

    results_text = sections.get('results', '')
    discussion_text = sections.get('discussion', '')

    # Combine results and discussion for outcome search
    full_text = results_text + '\n' + discussion_text

    for complication in COMPLICATION_TYPES:
        # Pattern 1: Look for numeric data in text (e.g., "pneumothorax: 5/100 (5%)")
        pattern = rf'{complication}[:\s]+(\d+)[/\s]+(\d+)\s*\(?([\d.]+)%\)?'
        m = re.search(pattern, full_text, re.IGNORECASE)

        if m:
            n = int(m.group(1))
            denominator = int(m.group(2))
            percent = float(m.group(3))

            # Look for CI in vicinity
            ci_lower, ci_upper = extract_ci_from_vicinity(full_text, m.start(), m.end())

            outcomes.append(OutcomeData(
                name=complication,
                n=n,
                denominator=denominator,
                percent=percent,
                ci_lower=ci_lower,
                ci_upper=ci_upper,
                evidence_text=m.group(0)
            ))

        else:
            # Pattern 2: Check if mentioned without numbers (link to table/figure)
            if complication in full_text.lower():
                # Look for "see Table X" or "Figure Y"
                ref_match = re.search(
                    rf'{complication}.*?(Table|Figure)\s+(\d+)',
                    full_text,
                    re.IGNORECASE
                )

                if ref_match:
                    outcomes.append(OutcomeData(
                        name=complication,
                        inconclusive=True,
                        linked_figure_table=f"{ref_match.group(1)} {ref_match.group(2)}",
                        evidence_text=ref_match.group(0)
                    ))

                # Pattern 3: Extract from tables
                table_outcome = extract_outcome_from_tables(complication, tables)
                if table_outcome:
                    outcomes.append(table_outcome)

    return outcomes


def extract_ci_from_vicinity(text: str, start: int, end: int, window: int = 100) -> tuple[Optional[float], Optional[float]]:
    """Extract confidence interval from text vicinity.

    Args:
        text: Full text
        start: Match start position
        end: Match end position
        window: Characters to search after match

    Returns:
        Tuple of (ci_lower, ci_upper) or (None, None)
    """
    vicinity = text[start:min(len(text), end+window)]

    # Pattern: 95% CI: 2-8% or (CI 2-8%)
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


def extract_outcome_from_tables(complication: str, tables: List[TableBlock]) -> Optional[OutcomeData]:
    """Extract outcome data from complications table.

    Args:
        complication: Complication name to find
        tables: Classified tables

    Returns:
        OutcomeData or None
    """
    # Look for complications tables
    for table in tables:
        if table.table_type != 'complications':
            continue

        # Search table rows for complication
        for row in table.rows:
            # Check if complication name in first cell
            if not row:
                continue

            first_cell = row[0].lower()
            if complication not in first_cell:
                continue

            # Extract numeric data from subsequent cells
            for cell in row[1:]:
                # Try n/N format
                fraction_match = re.search(r'(\d+)/(\d+)', cell)
                if fraction_match:
                    n = int(fraction_match.group(1))
                    denominator = int(fraction_match.group(2))
                    percent = (n / denominator * 100) if denominator > 0 else None

                    return OutcomeData(
                        name=complication,
                        n=n,
                        denominator=denominator,
                        percent=percent,
                        linked_figure_table=f"Table (page {table.page})",
                        evidence_text=cell,
                        page=table.page
                    )

                # Try percentage
                pct_match = re.search(r'([\d.]+)%', cell)
                if pct_match:
                    percent = float(pct_match.group(1))

                    return OutcomeData(
                        name=complication,
                        percent=percent,
                        linked_figure_table=f"Table (page {table.page})",
                        evidence_text=cell,
                        page=table.page
                    )

    return None


__all__ = [
    "extract_outcomes",
    "OutcomeData",
    "COMPLICATION_TYPES",
]
