"""Table classification and gating to reduce false positives."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TableData(BaseModel):
    """Raw table data from extraction."""
    title: Optional[str] = None
    headers: List[str]
    rows: List[List[str]]
    page: Optional[int] = None


class TableBlock(BaseModel):
    """Classified and validated table."""
    table_type: str
    caption: Optional[str] = None
    headers: List[str]
    rows: List[List[str]]
    page: Optional[int] = None
    confidence: float = 0.8


# Table type classification patterns
TABLE_TYPE_PATTERNS = {
    'diagnostic_accuracy': [
        'sensitivity', 'specificity', 'ppv', 'npv', 'auc', 'accuracy',
        'positive predictive value', 'negative predictive value',
        'roc', 'c-statistic'
    ],
    'baseline_characteristics': [
        'age', 'gender', 'sex', 'bmi', 'smoking', 'comorbidities',
        'baseline', 'demographics', 'characteristics', 'patient characteristics'
    ],
    'complications': [
        'complication', 'adverse event', 'pneumothorax', 'bleeding',
        'mortality', 'death', 'ctcae', 'grade', 'adverse effects'
    ],
    'outcomes': [
        'outcome', 'survival', 'progression', 'response', 'recurrence',
        'follow-up', 'endpoint'
    ],
    'diagnostic_yield': [
        'yield', 'diagnostic', 'diagnosis', 'malignancy', 'adequacy'
    ],
    'reasons_for_failure': [
        'failure', 'non-diagnostic', 'inadequate', 'unsuccessful',
        'technical failure'
    ]
}

# Medical/statistical terms that should appear in table headers
MEDICAL_GLOSSARY = [
    'n', '%', 'p-value', 'p value', 'ci', '95% ci', 'or', 'rr', 'hr',
    'age', 'sensitivity', 'specificity', 'auc', 'ppv', 'npv',
    'mean', 'median', 'sd', 'iqr', 'range', 'min', 'max',
    'total', 'patient', 'case', 'group', 'arm', 'control',
    'years', 'months', 'days', 'male', 'female',
]


def classify_and_gate_tables(tables: List[Any]) -> List[TableBlock]:
    """Apply classification and gating to filter real tables from false positives.

    Args:
        tables: Raw tables from extraction

    Returns:
        List of validated TableBlock objects
    """
    gated_tables = []

    for table in tables:
        # Convert to TableData if needed
        if not isinstance(table, TableData):
            table_data = _convert_to_table_data(table)
        else:
            table_data = table

        # Gate 1: Header allowlist (≥2 medical/unit headers)
        medical_headers = count_medical_headers(table_data.headers)
        if medical_headers < 2:
            continue  # Skip - likely not a real table

        # Gate 2: Paragraph check (reject prose mis-detected as tables)
        if is_paragraph_table(table_data):
            continue  # Skip - abstract or prose

        # Gate 3: Minimum size (at least 2 headers, 1 data row)
        if len(table_data.headers) < 2 or len(table_data.rows) < 1:
            continue

        if cell_exceeds_character_limit(table_data):
            continue

        if row_average_exceeds_threshold(table_data):
            continue

        # Classify table type
        table_type = classify_table_type(table_data)

        # Create validated TableBlock
        gated_tables.append(TableBlock(
            table_type=table_type,
            caption=table_data.title,
            headers=table_data.headers,
            rows=table_data.rows,
            page=table_data.page,
            confidence=0.85 if medical_headers >= 3 else 0.75
        ))

    return gated_tables


def _convert_to_table_data(raw_table: Any) -> TableData:
    """Convert raw table dict to TableData.

    Args:
        raw_table: Raw table from extraction (dict or other)

    Returns:
        TableData object
    """
    if isinstance(raw_table, dict):
        return TableData(
            title=raw_table.get('title') or raw_table.get('caption'),
            headers=raw_table.get('headers', []),
            rows=raw_table.get('rows', []),
            page=raw_table.get('page')
        )

    # Fallback
    return TableData(headers=[], rows=[])


def count_medical_headers(headers: List[str]) -> int:
    """Count how many headers match medical glossary or units.

    Args:
        headers: Table header strings

    Returns:
        Count of medical/statistical headers
    """
    count = 0

    for h in headers:
        h_lower = h.lower().strip()

        # Check exact match
        if h_lower in MEDICAL_GLOSSARY:
            count += 1
            continue

        # Check substring match
        if any(term in h_lower for term in MEDICAL_GLOSSARY):
            count += 1
            continue

        # Check for percentage symbol
        if '%' in h:
            count += 1
            continue

        # Check for numeric pattern (e.g., "n=123")
        if re.search(r'n\s*=\s*\d+', h_lower):
            count += 1
            continue

    return count


def is_paragraph_table(table: TableData) -> bool:
    """Check if table rows contain paragraph-like sentences (false positive).

    Args:
        table: Table to check

    Returns:
        True if table appears to be prose misclassified as table
    """
    prose_cells = 0
    total_cells = 0

    for row in table.rows:
        for cell in row:
            if not isinstance(cell, str) or len(cell.strip()) < 10:
                continue

            total_cells += 1

            # Check for long sentences
            sentences = re.split(r'[.!?]+', cell)
            clean_sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
            if clean_sentences:
                avg_words = sum(len(s.split()) for s in clean_sentences) / len(clean_sentences)
                if avg_words > 20:  # Paragraph-like
                    prose_cells += 1
                    continue

            # Check for high punctuation density
            if len(cell) > 50:  # Only check substantial cells
                punct_count = sum(1 for c in cell if c in '.,;:!?')
                punct_ratio = punct_count / len(cell)
                if punct_ratio > 0.10:  # >10% punctuation suggests prose
                    prose_cells += 1
                    continue

            # Check for narrative keywords
            narrative_markers = ['however', 'therefore', 'moreover', 'furthermore',
                               'although', 'thus', 'hence', 'consequently']
            if any(marker in cell.lower() for marker in narrative_markers):
                prose_cells += 1
                continue

            # Check for garbled text (common in bad extractions)
            if has_garbled_text(cell):
                prose_cells += 1
                continue

    # If more than 30% of cells look like prose, it's probably not a real table
    if total_cells > 0 and (prose_cells / total_cells) > 0.3:
        return True

    return False


def has_garbled_text(text: str) -> bool:
    """Check if text contains garbled/corrupted patterns.

    Args:
        text: Text to check

    Returns:
        True if text appears garbled
    """
    # Check for excessive special characters
    special_chars = sum(1 for c in text if c in '†‡§¶©®™≥≤±∞')
    if len(text) > 0 and special_chars / len(text) > 0.1:
        return True

    # Check for nonsense character sequences
    if re.search(r'[^\w\s]{5,}', text):  # 5+ consecutive non-alphanumeric
        return True

    # Check for excessive uppercase/lowercase alternation
    if re.search(r'([a-z][A-Z]){4,}|([A-Z][a-z]){4,}', text):
        return True

    return False


def classify_table_type(table: TableData) -> str:
    """Classify table using header and caption patterns.

    Args:
        table: Table to classify

    Returns:
        Table type string
    """
    # Combine caption and headers for matching
    search_text = ' '.join([
        table.title or '',
        ' '.join(table.headers)
    ]).lower()

    # Check each pattern set
    for table_type, patterns in TABLE_TYPE_PATTERNS.items():
        if any(p in search_text for p in patterns):
            return table_type

    return 'other'


def cell_exceeds_character_limit(table: TableData, limit: int = 600) -> bool:
    for row in table.rows:
        for cell in row:
            if isinstance(cell, str) and len(cell) > limit:
                return True
    return False


def row_average_exceeds_threshold(table: TableData, token_threshold: int = 120) -> bool:
    for row in table.rows:
        tokens = sum(len(cell.split()) for cell in row if isinstance(cell, str))
        cells = sum(1 for cell in row if isinstance(cell, str)) or 1
        if (tokens / cells) > token_threshold:
            return True
    return False


def extract_table_from_section(section_text: str, table_type: str) -> Optional[TableBlock]:
    """Extract inline table from prose (e.g., "Sensitivity 85%, Specificity 92%").

    Args:
        section_text: Section text potentially containing inline data
        table_type: Expected table type

    Returns:
        TableBlock if inline table detected, else None
    """
    # Look for diagnostic accuracy inline data
    if table_type == 'diagnostic_accuracy':
        metrics = {}

        # Extract sensitivity
        sens_match = re.search(r'sensitivity[:\s]+(\d+(?:\.\d+)?)%?', section_text, re.IGNORECASE)
        if sens_match:
            metrics['Sensitivity'] = f"{sens_match.group(1)}%"

        # Extract specificity
        spec_match = re.search(r'specificity[:\s]+(\d+(?:\.\d+)?)%?', section_text, re.IGNORECASE)
        if spec_match:
            metrics['Specificity'] = f"{spec_match.group(1)}%"

        # Extract PPV
        ppv_match = re.search(r'(?:ppv|positive predictive value)[:\s]+(\d+(?:\.\d+)?)%?', section_text, re.IGNORECASE)
        if ppv_match:
            metrics['PPV'] = f"{ppv_match.group(1)}%"

        # Extract NPV
        npv_match = re.search(r'(?:npv|negative predictive value)[:\s]+(\d+(?:\.\d+)?)%?', section_text, re.IGNORECASE)
        if npv_match:
            metrics['NPV'] = f"{npv_match.group(1)}%"

        if len(metrics) >= 2:
            # Create simple table
            return TableBlock(
                table_type='diagnostic_accuracy',
                caption='Diagnostic Performance (extracted from text)',
                headers=['Metric', 'Value'],
                rows=[[k, v] for k, v in metrics.items()],
                confidence=0.7
            )

    return None


__all__ = [
    "classify_and_gate_tables",
    "count_medical_headers",
    "is_paragraph_table",
    "classify_table_type",
    "extract_table_from_section",
    "TableBlock",
    "TableData",
]
