"""Article front-matter extraction with hierarchical title and metadata."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from medparse.ingest.models import PageData


def extract_title_hierarchical(pages: List[PageData]) -> Dict[str, Any]:
    """Extract title using hierarchical strategy.

    Try in order:
    1. Embedded PDF metadata
    2. First-page centered title block (largest font, centered)
    3. DOI resolver block (fetch from DOI if present)
    4. Running header fallback

    Returns:
        Dictionary with title, confidence, and source
    """
    if not pages:
        return {'title': None, 'confidence': 0.0, 'source': None}

    # Try PDF metadata first (if available in PageData)
    # Note: This would require extending PageData with metadata
    # For now, skip this step

    # Extract from first page layout (largest heading)
    if title := extract_centered_title_block(pages[0]):
        if is_valid_title(title):
            return {'title': title, 'confidence': 0.85, 'source': 'layout'}

    # DOI resolver fallback
    if doi := extract_doi(pages[:2]):
        # For now, just use DOI as indicator of title location
        # Real implementation would query CrossRef API
        pass

    # Running header (lowest confidence)
    if title := extract_running_header(pages[0]):
        if is_valid_title(title):
            return {'title': title, 'confidence': 0.6, 'source': 'header'}

    # Fallback to first heading
    if pages[0].headings:
        title = pages[0].headings[0].title
        if is_valid_title(title):
            return {'title': title, 'confidence': 0.5, 'source': 'first_heading'}

    return {'title': None, 'confidence': 0.0, 'source': None}


def is_valid_title(title: str) -> bool:
    """Validate title is not all-caps org name; must contain ≥3 words and ≥1 non-stopword.

    Args:
        title: Candidate title string

    Returns:
        True if valid title
    """
    if not title:
        return False

    words = title.split()
    if len(words) < 3:
        return False

    # Reject all-caps organizational names
    if title.isupper() and any(org in title for org in ['SOCIETY', 'ASSOCIATION', 'ORGANIZATION', 'JOURNAL', 'STATEMENT']):
        return False

    # Must have at least one non-stopword
    stopwords = {'the', 'a', 'an', 'of', 'for', 'in', 'on', 'at', 'to', 'and', 'or', 'but', 'by', 'with'}
    non_stopwords = [w for w in words if w.lower() not in stopwords]
    return len(non_stopwords) >= 1


def extract_centered_title_block(page: PageData) -> Optional[str]:
    """Extract title from first page using largest heading or centered text.

    Args:
        page: First page data

    Returns:
        Title string or None
    """
    # Try headings first (level 1)
    level_1_headings = [h for h in page.headings if h.level == 1]
    if level_1_headings:
        # Use first level-1 heading
        return level_1_headings[0].title

    # Fallback: look for centered text in first few lines
    if not page.lines:
        return None

    for line in page.lines[:10]:
        # Skip very short lines and lines with typical header content
        if len(line.split()) < 3:
            continue
        if any(kw in line.lower() for kw in ['copyright', '©', 'doi:', 'published', 'received']):
            continue

        # Check if line looks like a title (mixed case, longer than 20 chars)
        if len(line) > 20 and not line.isupper():
            return line.strip()

    return None


def extract_running_header(page: PageData) -> Optional[str]:
    """Extract title from running header (first line).

    Args:
        page: Page data

    Returns:
        Title from header or None
    """
    if not page.lines:
        return None

    first_line = page.lines[0].strip()

    # Skip if it looks like metadata
    if any(kw in first_line.lower() for kw in ['page', 'copyright', '©', 'doi:', 'vol.', 'issue']):
        return None

    if len(first_line) > 10:
        return first_line

    return None


def extract_doi(pages: List[PageData]) -> Optional[str]:
    """Extract DOI from first 2 pages.

    Args:
        pages: First pages to search

    Returns:
        DOI string or None
    """
    for page in pages:
        text = '\n'.join(page.lines)
        # DOI pattern: 10.xxxx/xxxxx
        match = re.search(r'\b(10\.\d{4,}/[^\s]+)', text, re.IGNORECASE)
        if match:
            doi = match.group(1)
            # Clean trailing punctuation
            doi = doi.rstrip('.,;:)')
            return doi

    return None


def extract_affiliations_and_correspondence(pages: List[PageData]) -> Dict[str, Any]:
    """Extract author affiliations and corresponding author from first page.

    Args:
        pages: Pages to search (typically first page)

    Returns:
        Dictionary with affiliations and corresponding_author
    """
    if not pages:
        return {'affiliations': {}, 'corresponding_author': None}

    first_page_text = '\n'.join(pages[0].lines)

    # Extract affiliations (superscript numbers/letters)
    affiliations = extract_superscript_affiliations(first_page_text)

    # Extract corresponding author (✉ or "Correspondence:" marker)
    corr_author = None
    for line in pages[0].lines:
        if '✉' in line or 'correspondence:' in line.lower():
            corr_author = extract_email_and_author(line)
            break

    return {
        'affiliations': affiliations,
        'corresponding_author': corr_author
    }


def extract_superscript_affiliations(text: str) -> Dict[str, str]:
    """Extract affiliations mapped by superscript numbers.

    Args:
        text: Text containing affiliation footnotes

    Returns:
        Dictionary mapping affiliation numbers to institution names
    """
    affiliations = {}

    # Pattern: "1 Department of...\n2 Division of..."
    # Look for numbered lines that mention institutions
    pattern = r'^(\d+)\s+([^\n]+(?:University|Hospital|Medical Center|Institute|Department|Division|School)[^\n]+)'
    matches = re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE)

    for m in matches:
        num = m.group(1)
        affiliation = m.group(2).strip()
        affiliations[num] = affiliation

    return affiliations


def extract_email_and_author(line: str) -> Optional[Dict[str, str]]:
    """Extract corresponding author and email from line.

    Args:
        line: Line containing correspondence info

    Returns:
        Dictionary with name and email or None
    """
    # Extract email
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line)
    email = email_match.group(0) if email_match else None

    # Extract name (before email or after "Correspondence:")
    name = None
    if 'correspondence:' in line.lower():
        # Extract name after "Correspondence:"
        parts = re.split(r'correspondence:', line, flags=re.IGNORECASE)
        if len(parts) > 1:
            name_part = parts[1].split(',')[0].split('(')[0].split('<')[0]
            name = name_part.strip()

    if email or name:
        return {'name': name, 'email': email}

    return None


def extract_coi_and_funding(pages: List[PageData]) -> Dict[str, List[str]]:
    """Extract conflicts of interest and funding statements.

    Args:
        pages: All pages to search

    Returns:
        Dictionary with conflicts and funding lists
    """
    full_text = '\n'.join('\n'.join(p.lines) for p in pages)

    # Extract COI section
    coi_section = extract_section_text(
        full_text,
        ['conflict of interest', 'conflicts of interest', 'disclosures', 'competing interests']
    )

    # Extract funding section
    funding_section = extract_section_text(
        full_text,
        ['funding', 'financial support', 'grant support', 'acknowledgments', 'acknowledgements']
    )

    return {
        'conflicts': parse_coi_statements(coi_section) if coi_section else [],
        'funding': parse_funding_statements(funding_section) if funding_section else []
    }


def extract_section_text(full_text: str, headings: List[str]) -> Optional[str]:
    """Extract text under any of the given headings.

    Args:
        full_text: Full document text
        headings: List of heading patterns to match

    Returns:
        Section text or None
    """
    for heading in headings:
        # Build pattern: heading followed by content until next section
        pattern = rf'(?:^|\n)({re.escape(heading)})[:\s]*\n(.+?)(?=\n\n[A-Z][a-z]+:|\Z)'
        match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(2).strip()

    return None


def parse_coi_statements(text: str) -> List[str]:
    """Parse COI section into list of statements.

    Args:
        text: COI section text

    Returns:
        List of COI statements
    """
    if not text:
        return []

    # Check for "none" declarations
    if re.search(r'\bnone\b|\bno\s+conflict', text, re.IGNORECASE):
        return ["None declared"]

    # Split by sentence or author name
    statements = []
    sentences = re.split(r'[.;]\s+', text)
    for sent in sentences:
        sent = sent.strip()
        if sent and len(sent) > 10:
            statements.append(sent)

    return statements


def parse_funding_statements(text: str) -> List[str]:
    """Parse funding section into list of grants/sources.

    Args:
        text: Funding section text

    Returns:
        List of funding statements
    """
    if not text:
        return []

    # Check for "none" declarations
    if re.search(r'\bnone\b|\bno\s+funding|\bnot\s+funded', text, re.IGNORECASE):
        return ["None"]

    # Extract grant numbers (e.g., "R01 HL123456", "NIH grant...")
    grants = re.findall(r'(?:grant|award)[\s#:]*([A-Z0-9-]+)', text, re.IGNORECASE)

    # Split by sentence
    statements = []
    sentences = re.split(r'[.;]\s+', text)
    for sent in sentences:
        sent = sent.strip()
        if sent and len(sent) > 15:
            statements.append(sent)

    return statements


__all__ = [
    "extract_title_hierarchical",
    "is_valid_title",
    "extract_affiliations_and_correspondence",
    "extract_coi_and_funding",
    "extract_doi",
]
