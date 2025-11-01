"""Utilities to strip headers/footers and restore whitespace in IFU text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HEADER_FOOTER_HINTS = [
    "IonSystem,Instruments,andAccessoriesUserManual",
    "553990-11Rev.C",
]

FUSE_RULES = [
    (re.compile(r"([A-Za-z])(\d)"), r"\1 \2"),
    (re.compile(r"(\d)([A-Za-z])"), r"\1 \2"),
    (re.compile(r"([a-z])([A-Z])"), r"\1 \2"),
    (re.compile(r"([.,;:])([A-Za-z0-9])"), r"\1 \2"),
]

# CamelCase fix pattern
CAMEL_FIX = re.compile(r'(?<=[a-z])(?=[A-Z][a-z])')  # fooBar -> foo Bar

# Ligature normalization
LIGATURE_MAP = {
    "\ufb01": "fi",  # ﬁ
    "\ufb02": "fl",  # ﬂ
    "\ufb00": "ff",  # ﬀ
    "\ufb03": "ffi",  # ﬃ
    "\ufb04": "ffl",  # ﬄ
}

BRAND_SUBSTITUTIONS = [
    (re.compile(r"\bplan\s*point\b", re.IGNORECASE), "PlanPoint"),
]


def strip_headers_footers(text: str) -> str:
    cleaned = text
    for hint in HEADER_FOOTER_HINTS:
        cleaned = cleaned.replace(hint, "")
    return cleaned


def normalize_ligatures(text: str) -> str:
    """Replace Unicode ligatures with standard ASCII equivalents."""
    for ligature, replacement in LIGATURE_MAP.items():
        text = text.replace(ligature, replacement)
    return text


def collapse_runs(s: str) -> str:
    """Collapse multiple whitespace into single space."""
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def heuristic_space_fix(s: str) -> str:
    """Fix missing spaces using CamelCase detection and common OCR artifacts."""
    s = CAMEL_FIX.sub(' ', s)
    s = s.replace('3 D', '3D')  # common OCR artifact
    for pattern, replacement in BRAND_SUBSTITUTIONS:
        s = pattern.sub(replacement, s)
    return collapse_runs(s)


def clean_paragraph(s: str) -> str:
    """Clean paragraph text with spacing restoration and normalization."""
    if not s:
        return s
    s = normalize_ligatures(s)
    s = heuristic_space_fix(s)
    return s


def restore_whitespace(text: str) -> str:
    """Simple whitespace restoration (legacy path)."""
    if not text:
        return text
    value = strip_headers_footers(text)
    value = normalize_ligatures(value)
    value = re.sub(r"[\t]+", " ", value)
    value = re.sub(r" *\n+", " ", value)
    for pattern, replacement in FUSE_RULES:
        value = pattern.sub(replacement, value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def rebuild_paragraphs_from_words(
    pdf_path: Path, page_numbers: List[int], y_tolerance: float = 2.0, x_gap_threshold: float = 3.0
) -> str:
    """Rebuild paragraphs using pdfplumber word extraction with proper spacing.

    Args:
        pdf_path: Path to the PDF file
        page_numbers: List of page numbers (1-indexed) to process
        y_tolerance: Vertical tolerance for grouping words into lines
        x_gap_threshold: Minimum horizontal gap to consider as a space

    Returns:
        Reconstructed text with proper spacing
    """
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        # Fallback to simple extraction if pdfplumber not available
        return ""

    paragraphs: List[str] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num in page_numbers:
                if page_num < 1 or page_num > len(pdf.pages):
                    continue

                page = pdf.pages[page_num - 1]
                words = page.extract_words(extra_attrs=["top", "bottom", "x0", "x1"])

                if not words:
                    continue

                # Group words by line (based on 'top' position)
                lines: Dict[float, List[Tuple[float, str]]] = {}
                for word in words:
                    top = round(word["top"], 1)
                    x0 = word["x0"]
                    text = word["text"]

                    # Find existing line within tolerance
                    matched_line = None
                    for line_top in lines:
                        if abs(line_top - top) <= y_tolerance:
                            matched_line = line_top
                            break

                    if matched_line is None:
                        lines[top] = [(x0, text)]
                    else:
                        lines[matched_line].append((x0, text))

                # Sort lines by vertical position (top to bottom)
                sorted_lines = sorted(lines.items(), key=lambda x: x[0])

                # Reconstruct each line with proper spacing
                for _, word_list in sorted_lines:
                    # Sort words by horizontal position (left to right)
                    word_list.sort(key=lambda x: x[0])

                    line_text = []
                    prev_x1 = None

                    for x0, text in word_list:
                        if prev_x1 is not None:
                            gap = x0 - prev_x1
                            if gap >= x_gap_threshold:
                                line_text.append(" ")

                        line_text.append(text)
                        # Estimate x1 based on character count (rough heuristic)
                        char_width = 6.0  # average char width in points
                        prev_x1 = x0 + len(text) * char_width

                    if line_text:
                        paragraphs.append("".join(line_text))

    except Exception:
        # Fallback on any error
        return ""

    # Join lines, merge hyphenated breaks, normalize ligatures
    full_text = " ".join(paragraphs)
    full_text = normalize_ligatures(full_text)
    # Merge hyphenated line breaks (e.g., "endo- luminal" → "endoluminal")
    full_text = re.sub(r"(\w)-\s+(\w)", r"\1\2", full_text)
    # Collapse multiple spaces
    full_text = re.sub(r"\s{2,}", " ", full_text)
    return full_text.strip()


def deep_cleanup_fields(ifu_json: Dict[str, object]) -> None:
    text_fields = [
        "indications_for_use",
        "intended_use",
        "intended_patient_population",
        "intended_user",
    ]
    for key in text_fields:
        value = ifu_json.get(key)
        if isinstance(value, str):
            ifu_json[key] = restore_whitespace(value)

    for block in ifu_json.get("safety_blocks", []) or []:
        if isinstance(block, dict):
            block["text"] = restore_whitespace(block.get("text", ""))

    for tbl in ifu_json.get("tables", []) or []:
        if not isinstance(tbl, dict):
            continue
        headers = tbl.get("headers") or []
        tbl["headers"] = [restore_whitespace(h) for h in headers]
        cleaned_rows: List[List[str]] = []
        for row in tbl.get("rows", []) or []:
            cleaned_rows.append([restore_whitespace(cell) for cell in row])
        tbl["rows"] = cleaned_rows


__all__ = [
    "restore_whitespace",
    "strip_headers_footers",
    "deep_cleanup_fields",
    "rebuild_paragraphs_from_words",
    "normalize_ligatures",
    "clean_paragraph",
    "collapse_runs",
    "heuristic_space_fix",
]
