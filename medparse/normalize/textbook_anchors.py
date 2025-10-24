"""Textbook chapter section mapping with TOC-aware extraction."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from medparse.ingest.models import PageData
from medparse.normalize.article_sections import is_toc_page, slice_between
from medparse.normalize.text_cleanup import clean_paragraph


# Standard textbook chapter section anchors
CHAPTER_SECTION_ANCHORS = {
    'introduction': ['introduction', 'overview', 'background'],
    'epidemiology': ['epidemiology', 'incidence', 'prevalence'],
    'pathophysiology': ['pathophysiology', 'pathogenesis', 'mechanism'],
    'clinical_presentation': ['clinical presentation', 'signs and symptoms', 'presentation'],
    'diagnosis': ['diagnosis', 'diagnostic approach', 'diagnostic evaluation'],
    'indications': ['indications', 'when to use', 'patient selection'],
    'contraindications': ['contraindications', 'when not to use', 'contraindicated'],
    'technique': ['technique', 'procedure', 'method', 'approach', 'procedural steps'],
    'complications': ['complications', 'adverse events', 'risks'],
    'outcomes': ['outcomes', 'results', 'efficacy'],
    'postoperative_care': ['postoperative', 'post-operative', 'post-procedure', 'follow-up'],
    'summary': ['summary', 'conclusions', 'key points', 'take-home messages'],
    'references': ['references', 'bibliography']
}


def build_section_map(pages: List[PageData]) -> Dict[str, Dict[str, any]]:
    """Build section map with {number, title, start_page, end_page}.

    Args:
        pages: Chapter pages

    Returns:
        Dictionary mapping section keys to section metadata
    """
    # Filter out TOC pages (critical - reuse IFU pattern)
    non_toc_pages = [p for p in pages if not is_toc_page('\n'.join(p.lines))]

    sections = {}

    # Extract each section
    for section_key, start_anchors in CHAPTER_SECTION_ANCHORS.items():
        # Build stop anchors (all other section headings)
        all_anchors = [a for anchors in CHAPTER_SECTION_ANCHORS.values() for a in anchors]
        stop_anchors = [a for a in all_anchors if a not in start_anchors]

        # Extract bounded section (reuse IFU slice_between pattern)
        section_text = slice_between(
            non_toc_pages,
            start_anchors=start_anchors,
            stop_anchors=stop_anchors,
            exclude_toc=True
        )

        if section_text:
            # Find start/end pages
            start_page = find_first_occurrence_page(non_toc_pages, start_anchors)
            end_page = find_first_occurrence_page(non_toc_pages, stop_anchors)

            if end_page is None or end_page <= start_page:
                end_page = len(non_toc_pages) - 1

            # Extract section number if present
            section_number = extract_section_number(section_text)

            # Post-process text
            clean_text = clean_paragraph(section_text)

            sections[section_key] = {
                'text': clean_text,
                'start_page': start_page,
                'end_page': end_page,
                'number': section_number
            }

    return sections


def extract_section_number(text: str) -> Optional[str]:
    """Extract section number (2.1, 2.1.1) from heading.

    Args:
        text: Section text

    Returns:
        Section number string or None
    """
    # Pattern: leading section number at start of text
    m = re.match(r'^(\d+(?:\.\d+)*)\s+', text)
    return m.group(1) if m else None


def find_first_occurrence_page(pages: List[PageData], anchors: List[str]) -> Optional[int]:
    """Find page number where any anchor first occurs.

    Args:
        pages: Pages to search
        anchors: Heading patterns to find

    Returns:
        Page number (0-indexed) or None
    """
    for i, page in enumerate(pages):
        page_text = '\n'.join(page.lines).lower()
        for anchor in anchors:
            if anchor.lower() in page_text:
                return i

    return None


def extract_keywords_clean(pages: List[PageData]) -> List[str]:
    """Extract keywords with scoping (only from Keywords block).

    Args:
        pages: Pages to search (typically first page)

    Returns:
        List of keyword strings
    """
    if not pages:
        return []

    first_page_text = '\n'.join(pages[0].lines)

    # Find keywords block
    kw_match = re.search(
        r'(?:Keywords|Key\s*words)[:\s]+(.+?)(?=\n\n|\n[A-Z]|$)',
        first_page_text,
        re.IGNORECASE | re.DOTALL
    )

    if not kw_match:
        return []

    kw_text = kw_match.group(1)

    # Split on semicolons or bullets
    keywords = re.split(r'[;•·]', kw_text)

    # Clean and validate
    cleaned = []
    for kw in keywords:
        kw = kw.strip()

        # Skip if too long (likely prose bleed)
        words = kw.split()
        if len(words) > 5:
            continue

        # Skip if contains commas (should be single phrases)
        if ',' in kw:
            # Unless it's part of a name like "EBUS, endobronchial ultrasound"
            if len(words) <= 5:
                kw = kw.replace(',', '')

        # Skip DOIs, emails
        if '@' in kw or 'doi' in kw.lower():
            continue

        if kw:
            cleaned.append(kw)

    return cleaned


__all__ = [
    "build_section_map",
    "extract_keywords_clean",
    "CHAPTER_SECTION_ANCHORS",
]
