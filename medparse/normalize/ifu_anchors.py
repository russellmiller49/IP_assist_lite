"""Anchor and lift key IFU clinical fields from raw text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .text_cleanup import rebuild_paragraphs_from_words, restore_whitespace, strip_headers_footers

H_IND = re.compile(r"^\s*Indications\s+for\s+Use\b", re.IGNORECASE | re.MULTILINE)
H_INTENDED = re.compile(r"^\s*Intended\s+Use\b", re.IGNORECASE | re.MULTILINE)
H_CONTRA = re.compile(r"^\s*Contraindications\b", re.IGNORECASE | re.MULTILINE)
H_AE = re.compile(r"^\s*(Adverse\s+Events|Complications)\b", re.IGNORECASE | re.MULTILINE)
STOP_RE = re.compile(r"^\s*(\d+\.\d+|[A-Z][^\n]{3,})", re.MULTILINE)
RX_RE = re.compile(r"\bRx\s*only\b", re.IGNORECASE)


def extract_section_after(text: str, heading: re.Pattern[str], stop: re.Pattern[str]) -> str | None:
    match = heading.search(text)
    if not match:
        return None
    tail = text[match.end() :]
    stop_match = stop.search(tail)
    if stop_match:
        body = tail[: stop_match.start()]
    else:
        body = tail
    cleaned = restore_whitespace(strip_headers_footers(body))
    return cleaned if cleaned else None


def _find_section_pages(text: str, heading: re.Pattern[str], pages_text: List[str]) -> Optional[List[int]]:
    """Find which page numbers contain a section (1-indexed)."""
    match = heading.search(text)
    if not match:
        return None

    # Find the page by looking at cumulative character counts
    cumulative = 0
    for idx, page_text in enumerate(pages_text):
        cumulative += len(page_text) + 1  # +1 for newline join
        if cumulative > match.start():
            # Section starts on this page; include next 2 pages for safety
            return list(range(idx + 1, min(idx + 4, len(pages_text) + 1)))
    return None


def lift_ifu_clinical_fields(pages_text: List[str], ifu_json: dict, pdf_path: Optional[Path] = None) -> None:
    """Lift clinical fields with optional pdfplumber-based whitespace restoration.

    Args:
        pages_text: Raw text from each page
        ifu_json: Output dictionary to populate
        pdf_path: Optional PDF path for pdfplumber word-level extraction
    """
    document_text = "\n".join(pages_text)

    # Indications for use (with pdfplumber enhancement if available)
    if pdf_path:
        ind_pages = _find_section_pages(document_text, H_IND, pages_text)
        if ind_pages:
            indications = rebuild_paragraphs_from_words(pdf_path, ind_pages)
            if indications:
                ifu_json["indications_for_use"] = indications

    if not ifu_json.get("indications_for_use"):
        indications = extract_section_after(document_text, H_IND, STOP_RE)
        if indications:
            ifu_json["indications_for_use"] = indications

    # Intended use (with pdfplumber enhancement if available)
    if pdf_path:
        intended_pages = _find_section_pages(document_text, H_INTENDED, pages_text)
        if intended_pages:
            intended = rebuild_paragraphs_from_words(pdf_path, intended_pages)
            if intended:
                ifu_json["intended_use"] = intended

    if not ifu_json.get("intended_use"):
        intended = extract_section_after(document_text, H_INTENDED, STOP_RE)
        if intended:
            ifu_json["intended_use"] = intended

    # Rx only lift → intended_user
    if RX_RE.search(document_text):
        ifu_json["intended_user"] = "Rx only"

    # Contraindications and adverse events (default to empty lists)
    contraindications = extract_section_after(document_text, H_CONTRA, STOP_RE)
    adverse_events = extract_section_after(document_text, H_AE, STOP_RE)

    ifu_json["contraindications"] = [contraindications] if contraindications else []
    ifu_json["adverse_events"] = [adverse_events] if adverse_events else []


__all__ = ["lift_ifu_clinical_fields"]
