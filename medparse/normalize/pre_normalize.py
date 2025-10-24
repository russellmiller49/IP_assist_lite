"""Unified pre-normalization for PDF-assembled text.

Applies surgical fixes to common concatenation and spacing issues
before pattern matching. Idempotent and targeted to avoid over-match.
"""

from __future__ import annotations

import re


def pre_normalize(text: str) -> str:
    """Pre-normalize PDF-ish text to look like realistic assembled text.

    Fixes common run-togethers, spacing issues, and OCR artifacts
    before any regex matching. Idempotent and safe.

    Args:
        text: Raw text from PDF extraction

    Returns:
        Normalized text ready for pattern matching
    """
    t = text

    # Fix common run-togethers for front-matter
    t = re.sub(r'(?i)\bPN(?=\d)', 'PN ', t)  # PN553990 → PN 553990
    # Rev patterns: handle Rev.C and RevC but NOT Revision
    t = re.sub(r'(?i)Rev\.([A-Z0-9])', r'Rev \1', t)  # Rev.C → Rev C (anywhere)
    t = re.sub(r'(?i)Rev(?!ision)(?=[A-Z0-9])', 'Rev ', t)  # RevC → Rev C (but not Revision)
    t = re.sub(r'(?i)\b(Intuitive Surgical),?\s+Inc\.?', r'\1, Inc.', t)

    # Split brand tokens when concatenated
    t = re.sub(r'(?i)\bIonOS\b', 'Ion OS', t)  # IonOS → Ion OS
    t = re.sub(r'(?i)\bPlanPoint\b', 'Plan Point', t)  # PlanPoint → Plan Point
    t = re.sub(r'(?i)\b(Plan Point)(Software|OS)\b', r'\1 \2', t)  # Plan PointSoftware → Plan Point Software

    # Split model numbers: 2024.08IF1000 → 2024.08 IF1000
    t = re.sub(r'(?<=\d)(?=[A-Z]{2}\d{3,4}\b)', ' ', t)

    # Normalize version lead-in (v/V/version)
    t = re.sub(r'(?i)\bV(?=\s*\d)', 'v', t)  # V 4.0 → v 4.0
    t = re.sub(r'(?i)\bversion(?=\s*\d)', 'v', t)  # version 3.0 → v 3.0

    # Remove stray spaces inside dotted versions: 6. 0. 0 → 6.0.0
    t = re.sub(r'\.\s+(?=\d)', '.', t)
    # Remove spaces around date separators: 2024 . 08 → 2024.08, 2024 - 08 → 2024-08, 2024 / 08 → 2024/08
    t = re.sub(r'(?<=\d)\s*([./-])\s*(?=\d)', r'\1', t)
    # Remove stray HORIZONTAL spaces between digits (preserve newlines!)
    t = re.sub(r'(?<=\d)[ \t]+(?=\d)', '', t)

    # Rare OCR noise between product and v: Ion OS 1 v6.0.0 → Ion OS v6.0.0
    t = re.sub(
        r'(?i)\b(Ion\s*OS|Plan\s*Point(?:\s*(?:Software|OS))?)\s*\d{1}\s*(?=v)',
        r'\1 ',
        t
    )

    # Whitespace collapse
    t = re.sub(r'[ \t]{2,}', ' ', t)

    return t


__all__ = ["pre_normalize"]
