"""Title extraction with font-aware and position-based heuristics."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from medparse.ingest.models import PageData


def extract_title(
    pages: List[PageData],
    metadata: Optional[Dict] = None,
    doi: Optional[str] = None,
) -> Tuple[Optional[str], str, float]:
    """Extract document title using multiple strategies.

    Args:
        pages: List of page data objects
        metadata: Optional PDF metadata
        doi: Optional DOI for fallback

    Returns:
        Tuple of (title, source, confidence)
        - title: The extracted title or None
        - source: 'layout'|'metadata'|'doi'|'header'
        - confidence: 0.0 to 1.0
    """

    # Strategy 1: Layout-based extraction from first page
    if pages:
        title, confidence = _extract_layout_title(pages[0])
        if title and confidence > 0.7:
            return _clean_title(title), 'layout', confidence

    # Strategy 2: PDF metadata
    if metadata and 'title' in metadata:
        meta_title = metadata['title']
        if meta_title and len(meta_title) > 10:
            return _clean_title(meta_title), 'metadata', 0.8

    # Strategy 3: DOI lookup (placeholder - would need external API)
    if doi:
        # In production, this would query CrossRef or similar
        # For now, just use DOI as indicator
        return None, 'doi', 0.0

    # Strategy 4: Running header detection
    if pages and len(pages) > 1:
        header_title = _extract_from_headers(pages)
        if header_title:
            return _clean_title(header_title), 'header', 0.5

    return None, 'unknown', 0.0


def _extract_layout_title(page: PageData) -> Tuple[Optional[str], float]:
    """Extract title from first page using font/position heuristics.

    Args:
        page: First page data

    Returns:
        Tuple of (title, confidence)
    """

    if not page.lines:
        return None, 0.0

    # Get lines from top 35% of page
    page_height = getattr(page, 'height', 792)  # Default US Letter height
    top_cutoff = page_height * 0.35

    candidate_lines = []

    # Simple heuristic: look for title-like patterns in first 10 lines
    for i, line in enumerate(page.lines[:15]):
        if not line or not line.strip():
            continue

        # Skip organization headers and document types
        skip_patterns = [
            r'^American Thoracic Society\s*Documents?$',
            r'^Guidelines?$',
            r'^Original\s+Articles?$',
            r'^Research\s+Articles?$',
            r'^Clinical\s+Practice\s+Guidelines?$',
            r'^Official\s+ATS.*Documents?$',
            r'^\s*\d+\s*$',  # Page numbers
            r'^Vol\.\s*\d+',  # Volume indicators
            r'^Downloaded from',  # Download notices
        ]

        if any(re.match(pattern, line.strip(), re.IGNORECASE) for pattern in skip_patterns):
            continue

        # Check for title indicators
        title_indicators = [
            len(line) > 20,  # Reasonable length
            not line.strip().endswith('.'),  # Titles rarely end with period
            any(word[0].isupper() for word in line.split() if word),  # Has capitals
            not re.match(r'^\d{4}[;\s]', line),  # Not starting with year
        ]

        if sum(title_indicators) >= 3:
            candidate_lines.append(line.strip())

    if not candidate_lines:
        return None, 0.0

    # Merge consecutive title lines
    title_parts = []
    for line in candidate_lines[:3]:  # Take max 3 lines
        # Remove ligatures and clean
        cleaned = _clean_line(line)
        if cleaned and len(cleaned) > 10:
            title_parts.append(cleaned)

    if title_parts:
        merged_title = ' '.join(title_parts)

        # Calculate confidence based on title quality
        confidence = 0.5
        if len(merged_title) > 30:
            confidence += 0.2
        if ':' in merged_title or '–' in merged_title:  # Has subtitle
            confidence += 0.15
        if any(word in merged_title.lower() for word in ['guideline', 'statement', 'recommendations']):
            confidence += 0.15

        return merged_title, min(confidence, 1.0)

    return None, 0.0


def _extract_from_headers(pages: List[PageData]) -> Optional[str]:
    """Extract title from running headers across pages.

    Args:
        pages: List of pages

    Returns:
        Most common header that looks like a title
    """

    header_candidates = {}

    for page in pages[1:min(5, len(pages))]:  # Check pages 2-5
        if not page.lines:
            continue

        # Look at first 2 lines
        for line in page.lines[:2]:
            if not line or len(line) < 20:
                continue

            cleaned = _clean_line(line)

            # Skip page numbers and dates
            if re.match(r'^[\d\s,/-]+$', cleaned):
                continue
            if re.match(r'^\d{4}[;\s]', cleaned):
                continue

            # Skip if it's just "Guideline 545" or similar (running header)
            if re.match(r'^Guideline\s+\d+$', cleaned, re.IGNORECASE):
                continue

            header_candidates[cleaned] = header_candidates.get(cleaned, 0) + 1

    if header_candidates:
        # Return most common header
        most_common = max(header_candidates.items(), key=lambda x: x[1])
        if most_common[1] >= 2:  # Appears on at least 2 pages
            return most_common[0]

    return None


def _clean_line(text: str) -> str:
    """Clean a text line by removing ligatures and normalizing spaces.

    Args:
        text: Raw text line

    Returns:
        Cleaned text
    """

    if not text:
        return ''

    # Replace common ligatures
    ligatures = {
        '\ufb01': 'fi',
        '\ufb02': 'fl',
        '\ufb03': 'ffi',
        '\ufb04': 'ffl',
        '\ufb00': 'ff',
        '\u0153': 'oe',
        '\u0152': 'OE',
        '\u00e6': 'ae',
        '\u00c6': 'AE',
    }

    result = text
    for ligature, replacement in ligatures.items():
        result = result.replace(ligature, replacement)

    # Normalize whitespace
    result = ' '.join(result.split())

    # Remove hyphenation at line breaks
    result = re.sub(r'-\s+', '', result)

    return result.strip()


def _clean_title(title: str) -> str:
    """Final cleaning and normalization of extracted title.

    Args:
        title: Raw extracted title

    Returns:
        Cleaned title
    """

    if not title:
        return ''

    # Clean with base function
    title = _clean_line(title)

    # Remove "Guideline 545" or similar page headers at the beginning
    title = re.sub(r'^Guideline\s+\d+\s+', '', title, flags=re.IGNORECASE)

    # Remove trailing organization names if they appear at the end
    org_suffixes = [
        r'\s+American Thoracic Society.*$',
        r'\s+ATS/ERS/JRS/ALAT.*$',
        r'\s+Official.*Statement.*$',
        r'\s+\d{4}\s*$',  # Trailing years
    ]

    for suffix in org_suffixes:
        title = re.sub(suffix, '', title, flags=re.IGNORECASE)

    # Collapse multiple spaces
    title = ' '.join(title.split())

    # Ensure proper capitalization for acronyms
    acronyms = ['ATS', 'ERS', 'ACCP', 'CHEST', 'EBUS', 'EUS', 'TBNA', 'CT', 'PET', 'MRI', 'NSCLC']
    for acronym in acronyms:
        title = re.sub(f'\\b{acronym.lower()}\\b', acronym, title, flags=re.IGNORECASE)

    return title.strip()


__all__ = ['extract_title']