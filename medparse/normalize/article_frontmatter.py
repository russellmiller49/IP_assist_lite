"""Article front-matter extraction with hierarchical title and metadata."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from medparse.ingest.models import PageData
from medparse.normalize.title_block import extract_title

NAME_EXCLUSION_TERMS = {
    "department",
    "university",
    "hospital",
    "institute",
    "center",
    "centre",
    "school",
    "division",
    "laboratory",
}

DEGREE_TOKENS = {"md", "phd", "do", "mba", "ms", "msc", "mph", "mbbs", "frcp"}
SUFFIX_TOKENS = {"jr", "sr", "ii", "iii", "iv", "v"}


def extract_title_hierarchical(
    pages: List[PageData],
    *,
    metadata: Optional[Dict[str, Any]] = None,
    doi: Optional[str] = None,
    fallback: Optional[str] = None,
) -> Dict[str, Any]:
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
        return {"title": fallback, "confidence": 0.0, "source": "fallback" if fallback else None}

    first_page = pages[0]

    # Strategy 1: font/layout-aware extractor
    layout_title, layout_source, layout_conf = extract_title(pages, metadata=metadata, doi=doi)
    if layout_source == "layout" and layout_title and is_valid_title(layout_title):
        return {"title": layout_title, "confidence": max(layout_conf, 0.85), "source": "layout"}

    # Strategy 2: PDF metadata (if provided)
    meta_title = (metadata or {}).get("title") if metadata else None
    if meta_title and is_valid_title(meta_title):
        return {"title": meta_title.strip(), "confidence": 0.8, "source": "metadata"}

    # Strategy 3: layout block heuristic
    layout_block = extract_centered_title_block(first_page)
    if layout_block and is_valid_title(layout_block):
        return {"title": layout_block, "confidence": 0.78, "source": "layout_block"}

    # Strategy 4: DOI (placeholder for resolver fetch)
    if doi:
        doi_hint = extract_doi(pages[:2])
        if doi_hint and doi_hint == doi:
            # Without resolver data we can only record provenance
            return {"title": None, "confidence": 0.0, "source": "doi"}

    # Strategy 5: running header (guarded)
    header_title = extract_running_header(first_page)
    if layout_source == "header" and layout_title and is_valid_title(layout_title):
        header_title = layout_title
    if header_title and is_valid_title(header_title):
        return {"title": header_title, "confidence": max(layout_conf, 0.55), "source": "header"}

    # Strategy 6: first heading on page
    if first_page.headings:
        heading_title = first_page.headings[0].title
        if heading_title and is_valid_title(heading_title):
            return {"title": heading_title, "confidence": 0.5, "source": "heading"}

    # Final fallback: filename-derived title
    if fallback:
        normalized = fallback.replace("_", " ").strip()
        if normalized:
            return {"title": normalized, "confidence": 0.25, "source": "filename"}

    return {"title": None, "confidence": 0.0, "source": None}


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

    lowered_title = title.lower()
    if "doi" in lowered_title or "http" in lowered_title or "www." in lowered_title:
        return False

    # Reject all-caps organizational names
    if title.isupper() and any(org in title for org in ['SOCIETY', 'ASSOCIATION', 'ORGANIZATION', 'JOURNAL', 'STATEMENT', 'GUIDELINE']):
        return False

    # Must have at least one non-stopword
    stopwords = {'the', 'a', 'an', 'of', 'for', 'in', 'on', 'at', 'to', 'and', 'or', 'but', 'by', 'with'}
    non_stopwords = [w for w in words if w.lower() not in stopwords]
    if len(non_stopwords) < 1:
        return False

    alpha = sum(1 for c in title if c.isalpha())
    digits = sum(1 for c in title if c.isdigit())
    if alpha == 0 or digits > alpha:
        return False

    return True


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

    collected: List[str] = []
    org_tokens = {"society", "college", "association", "journal", "thoracic"}
    stop_prefixes = (
        "An Official",
        "Official",
        "This Official",
        "Keywords",
        "Author",
        "Correspondence",
        "Received",
        "Accepted",
        "Published",
        "©",
    )
    skip_contains = ("doi", "http", "https", "www.", "vol.", "volume ")

    for line in page.lines[:20]:
        candidate = line.strip()
        if not candidate:
            if collected:
                break
            continue

        lower = candidate.lower()
        if any(kw in lower for kw in ['copyright', '©', 'doi:', 'published', 'received', 'accepted', 'submitted']):
            if collected:
                break
            continue
        if any(token in lower for token in skip_contains):
            continue

        if any(candidate.startswith(prefix) for prefix in stop_prefixes) and collected:
            break

        words = candidate.split()
        if len(words) < 2 and candidate.isupper():
            continue

        if not collected and candidate.isupper() and any(token in lower for token in org_tokens):
            continue

        collected.append(candidate)

        if len(" ".join(collected)) > 180:
            break

    filtered: List[str] = []
    for segment in collected:
        lower = segment.lower()
        if not filtered and segment.isupper() and any(token in lower for token in org_tokens):
            continue
        filtered.append(segment)

    if filtered:
        return " ".join(filtered)

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


def extract_bibliographic_metadata(pages: List[PageData]) -> Dict[str, Any]:
    """Extract journal/year/volume information from early pages."""

    if not pages:
        return {}

    search_lines = []
    for page in pages[:2]:
        search_lines.extend(page.lines[:40])

    journal = None
    year = None
    volume = None
    issue = None

    for line in search_lines:
        cleaned = line.strip()
        if not cleaned or len(cleaned) < 6:
            continue
        match = re.search(r'([A-Za-z][A-Za-z\s&\-]+?)\s+(\d{4})\s*;\s*(\d+)(?:\s*\(([^)]+)\))?', cleaned)
        if match:
            journal = match.group(1).strip()
            year = int(match.group(2)) if match.group(2) else None
            volume = match.group(3)
            issue = match.group(4)
            break

    if year is None:
        for line in search_lines:
            year_match = re.search(r'\b(19|20)\d{2}\b', line)
            if year_match:
                year = int(year_match.group(0))
                break

    payload: Dict[str, Any] = {}
    if journal:
        payload['journal'] = journal
    if year:
        payload['year'] = year
    if volume:
        payload['volume'] = volume
    if issue:
        payload['issue'] = issue
    return payload


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


def extract_authors_affiliations(pages: List[PageData]) -> Dict[str, Any]:
    """Return structured author and affiliation details from early pages."""

    if not pages:
        return {"authors": [], "affiliations": [], "corresponding_author": None}

    first_page = pages[0]
    header_lines: List[str] = []
    for line in first_page.lines[:30]:
        cleaned = line.strip()
        if not cleaned:
            continue
        if re.match(r"(abstract|summary|keywords)\b", cleaned, re.IGNORECASE):
            break
        header_lines.append(cleaned)

    header_block = " ".join(header_lines)
    header_block = re.sub(r"\s+", " ", header_block)
    header_block = header_block.replace(" and ", ", ")

    # Trim leading metadata before the first name-like pattern
    name_start = re.search(r"[A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-z]+(?=\s*\d)", header_block)
    if not name_start:
        name_start = re.search(r"[A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-z]+", header_block)
    if name_start:
        header_block = header_block[name_start.start():]

    # Drop trailing publication metadata (received/accepted/etc.)
    trailer_split = re.split(r"\b(Received|Accepted|Published|Copyright|©)\b", header_block, maxsplit=1)
    if trailer_split:
        header_block = trailer_split[0].strip()

    all_affiliations = extract_superscript_affiliations("\n".join(first_page.lines[:80]))

    authors: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for token in _tokenise_author_block(header_block):
        if not token:
            continue

        markers = re.findall(r"[\d]+|[†‡*]", token)
        clean_token = re.sub(r"[\d†‡*]+", "", token).strip()

        if not _looks_like_name(clean_token):
            continue

        given, family, suffix = _split_name(clean_token)
        if not family:
            continue

        normalized = f"{given.lower()}_{family.lower()}"
        if normalized in seen:
            continue
        seen.add(normalized)

        authors.append(
            {
                "given": given,
                "family": family,
                "suffix": suffix,
                "footnotes": markers,
            }
        )

    if not authors:
        fallback_lines = _fallback_author_lines(first_page)
        fallback_block = ", ".join(fallback_lines)
        for token in _tokenise_author_block(fallback_block):
            clean_token = re.sub(r"[\d†‡*]+", "", token).strip()
            if not _looks_like_name(clean_token):
                continue
            given, family, suffix = _split_name(clean_token)
            if not family:
                continue
            normalized = f"{given.lower()}_{family.lower()}"
            if normalized in seen:
                continue
            seen.add(normalized)
            authors.append(
                {
                    "given": given,
                    "family": family,
                    "suffix": suffix,
                    "footnotes": [],
                }
            )

    affiliation_records = [
        {"id": aff_id, "text": text}
        for aff_id, text in all_affiliations.items()
    ]

    corresponding = extract_affiliations_and_correspondence(pages).get("corresponding_author")

    return {
        "authors": authors,
        "affiliations": affiliation_records,
        "corresponding_author": corresponding,
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


def _tokenise_author_block(block: str) -> List[str]:
    """Split combined author line into candidate tokens."""

    if not block:
        return []

    block = block.replace("·", ",")
    block = re.sub(
        r"\((?:MD|PhD|DO|MBA|MS|MSc|MPH|MBBS|FRCP|FRCPath|DDS|RN)[^)]*\)",
        "",
        block,
        flags=re.IGNORECASE,
    )
    parts = re.split(r",\s*|\s+;\s*", block)
    return [part.strip() for part in parts if part.strip()]


def _looks_like_name(token: str) -> bool:
    """Heuristic check that ``token`` appears to be a personal name."""

    if not token or len(token.split()) < 2:
        return False
    if len(token.split()) > 6:
        return False
    if ":" in token:
        return False
    if token.isupper():
        return False

    lowered = token.lower()
    if any(term in lowered for term in NAME_EXCLUSION_TERMS):
        return False

    letters = sum(1 for ch in token if ch.isalpha())
    return letters / max(len(token), 1) >= 0.6


def _split_name(name: str) -> Tuple[str, str, Optional[str]]:
    """Split a full name into given/family/suffix components."""

    cleaned = re.sub(
        r"\b(" + "|".join(DEGREE_TOKENS) + r")\b\.?",
        "",
        name,
        flags=re.IGNORECASE,
    )
    parts = [part for part in cleaned.replace(".", "").split() if part]
    if len(parts) < 2:
        return cleaned.strip(), "", None

    suffix = None
    if parts[-1].lower() in SUFFIX_TOKENS:
        suffix = parts.pop()

    family = parts[-1]
    given = " ".join(parts[:-1])
    return given.strip(), family.strip(), suffix


def _fallback_author_lines(page: PageData) -> List[str]:
    """Collect lines that look like author listings as a last resort."""

    candidates: List[str] = []
    for line in page.lines[:60]:
        cleaned = line.strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered.startswith(("abstract", "summary", "keywords", "introduction")):
            break
        if any(
            term in lowered
            for term in (
                "guideline",
                "statement",
                "journal",
                "supplement",
                "doi",
                "www.",
                "copyright",
            )
        ):
            continue
        if re.search(r"\b[A-Z][a-zA-Z]+(?:[-\s][A-Z][a-zA-Z]+)+", cleaned):
            candidates.append(cleaned)
    return candidates


__all__ = [
    "extract_title_hierarchical",
    "is_valid_title",
    "extract_affiliations_and_correspondence",
     "extract_authors_affiliations",
    "extract_coi_and_funding",
    "extract_doi",
]
