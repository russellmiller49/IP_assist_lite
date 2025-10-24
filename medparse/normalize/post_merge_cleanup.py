"""Post-merge text cleanup for IFU content.

Fixes whitespace, running headers, and device name spacing after layout merge.
"""

from __future__ import annotations

import re
from typing import List


def clean_merged_text(text: str, *, remove_headers: bool = True) -> str:
    """Clean text after layout merge.

    Args:
        text: Merged text from page content
        remove_headers: Whether to remove running headers/footers

    Returns:
        Cleaned text
    """
    if not text:
        return text

    # 1. Fix hyphenation across line breaks
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)

    # 2. Fix run-together words (lowercase→Uppercase boundaries)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # 3. Known device terms spacing
    text = re.sub(r'\bIonendoluminal\b', 'Ion endoluminal', text, flags=re.IGNORECASE)
    text = re.sub(r'\bVisionProbe\b', 'Vision Probe', text, flags=re.IGNORECASE)

    # 4. Remove running headers/footers if requested
    if remove_headers:
        text = _remove_running_headers(text)

    # 5. Collapse multiple spaces/newlines
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def _remove_running_headers(text: str) -> str:
    """Remove running headers and footers.

    Patterns:
        - Page numbers + section titles: "12 Introduction | Professional Instructions..."
        - Standalone page numbers at line start
        - "Table of Contents" at line start
    """
    lines = text.split('\n')
    cleaned: List[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip lines that start with page number + section title
        if re.match(r'^\d+\s+(Introduction|Table of Contents|Professional Instructions|User Manual)\b', stripped, re.IGNORECASE):
            continue

        # Skip standalone page numbers (1-3 digits at line start)
        if re.match(r'^\d{1,3}$', stripped):
            continue

        # Skip "Table of Contents" header
        if re.match(r'^Table of Contents\s*$', stripped, re.IGNORECASE):
            continue

        cleaned.append(line)

    return '\n'.join(cleaned)


def clean_device_names(text: str) -> str:
    """Fix spacing in device/product names.

    Args:
        text: Input text with potential spacing issues

    Returns:
        Text with corrected device names
    """
    replacements = [
        # Ion system variants
        (r'\bIon\s*endoluminal\s*system\b', 'Ion Endoluminal System'),
        (r'\bIonendoluminalsystem\b', 'Ion Endoluminal System'),
        (r'\bIntuitive\s*Ion\b', 'Intuitive Ion'),

        # Other devices
        (r'\bPlanPoint\s*software\b', 'PlanPoint Software'),
        (r'\bVision\s*Probe\b', 'Vision Probe'),
    ]

    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


__all__ = ["clean_merged_text", "clean_device_names"]
