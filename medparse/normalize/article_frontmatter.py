"""Article front-matter extraction with hierarchical title and metadata."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from medparse.ingest.models import PageData
from medparse.normalize.title_block import extract_title
from medparse.utils.log import get_logger

if TYPE_CHECKING:
    from medparse.schema.article import Affiliation, Author

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
    "society",
    "statement",
    "classification",
    "update",
    "guideline",
    "respiratory",
    "international",
    "committee",
    "thoracic",
}

DEGREE_TOKENS = {"md", "phd", "do", "mba", "ms", "msc", "mph", "mbbs", "frcp"}
SUFFIX_TOKENS = {"jr", "sr", "ii", "iii", "iv", "v"}
SUPERSCRIPT_TRANSLATION = str.maketrans({
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
})
SUPERSCRIPT_CLASS = "\u2070\u00B9\u00B2\u00B3\u2074\u2075\u2076\u2077\u2078\u2079"

LOGGER = get_logger(__name__)

HEADER_NOISE_TITLES = {
    "american thoracic society documents",
    "american thoracic society document",
    "official american thoracic society documents",
    "guideline",
}

TITLE_SKIP_KEYWORDS = {
    "guideline",
    "guidelines",
    "esge",
    "ers",
    "ests",
    "ats",
    "accp",
    "sign",
    "statements",
}

RUNNING_HEADER_PATTERNS = [
    re.compile(r"\bguideline\s*\d+\b", re.IGNORECASE),
    re.compile(r"\bamerican thoracic society documents\b", re.IGNORECASE),
    re.compile(r"^\s*©"),
    re.compile(r"^\s*copyright", re.IGNORECASE),
]

AUTHOR_PREFIX_PATTERN = re.compile(r"^\s*author(?:s)?[:\-]\s*", re.IGNORECASE)
AUTHOR_NAME_PATTERN = re.compile(
    r"""
    ^
    (?P<first>[A-Z][a-zA-Z]*(?:[-'][A-Z][a-zA-Z]*)*)
    (?:\s+(?:[A-Z]\.|[A-Z][a-zA-Z]*(?:[-'][A-Z][a-zA-Z]*)*)){1,3}
    (?:\s+(?:Jr|Sr|II|III|IV|V))?
    $
    """,
    re.VERBOSE,
)

AFFILIATION_HEADING_PATTERN = re.compile(
    r"^\s*(affiliations?|author information|author affiliations?|institution(?:s)?|author details)\s*[:\-]?\s*$",
    re.IGNORECASE,
)
AFFILIATION_STOP_PATTERN = re.compile(
    r"^\s*(keywords|key words|abstract|summary|introduction|correspondence|address for correspondence|contact)\b",
    re.IGNORECASE,
)
AFFILIATION_MARKER_LINE = re.compile(
    r"^\s*(?:\d{1,2}(?:\s*,\s*\d{1,2})*|[A-Za-z]|[†‡*]+)[\s\.)-]+.*$"
)


def _collect_affiliation_text(pages: List[PageData], max_pages: int = 2) -> str:
    if not pages:
        return ""

    collected: List[str] = []
    capture = False

    for page in pages[:max_pages]:
        for raw_line in page.lines or []:
            stripped = raw_line.strip()
            if not stripped:
                if capture:
                    collected.append("")
                continue

            if AFFILIATION_HEADING_PATTERN.match(stripped):
                capture = True
                continue

            if capture and AFFILIATION_STOP_PATTERN.match(stripped):
                capture = False
                continue

            if capture:
                collected.append(stripped)
                continue

            if AFFILIATION_MARKER_LINE.match(stripped):
                collected.append(stripped)

    return "\n".join(collected)


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
    def _should_skip_line(line: str) -> bool:
        cleaned = line.strip()
        if not cleaned:
            return True
        lowered = cleaned.lower()
        if any(pattern.search(cleaned) for pattern in RUNNING_HEADER_PATTERNS):
            return True
        if len(cleaned) <= 4 and cleaned.isdigit():
            return True
        if any(keyword in lowered for keyword in TITLE_SKIP_KEYWORDS):
            words = cleaned.split()
            if cleaned.isupper() or len(words) <= 2 or re.search(r"\b\d{1,3}\b", cleaned):
                return True
        return False

    def _merge_segments(segments: List[str]) -> str:
        collapsed: List[str] = []
        for segment in segments:
            if not collapsed:
                collapsed.append(segment)
                continue
            if collapsed[-1].endswith(":"):
                collapsed[-1] = f"{collapsed[-1]} {segment}"
            else:
                collapsed.append(segment)
        return " ".join(collapsed)

    """Extract title from first page using largest heading or centered text.

    Args:
        page: First page data

    Returns:
        Title string or None
    """
    # Try headings first (level 1)
    level_1_headings = [h for h in page.headings if h.level == 1]
    if level_1_headings:
        candidate = level_1_headings[0].title
        if candidate and is_valid_title(candidate) and candidate.strip().lower() not in HEADER_NOISE_TITLES:
            return candidate

    block_segments: List[str] = []
    blocks = [
        block
        for block in (page.blocks or [])
        if block.text and (block.font_size or 0) > 0
    ]
    if blocks:
        max_font = max(block.font_size or 0 for block in blocks)
        # Allow a small tolerance in font size in case of mixed typography
        high_blocks = [
            block
            for block in blocks
            if (block.font_size or 0) >= max_font * 0.92
        ]
        high_blocks.sort(key=lambda blk: blk.bbox[1] if blk.bbox else 0.0)
        last_baseline: Optional[float] = None
        for block in high_blocks:
            lines = [line.strip() for line in block.text.splitlines() if line.strip()]
            lines = [line for line in lines if not _should_skip_line(line)]
            if not lines:
                continue
            if last_baseline is not None and block.bbox and block.bbox[1] - last_baseline > 80:
                # Title blocks are typically contiguous; stop when spacing jumps significantly
                break
            block_segments.extend(lines)
            if block.bbox:
                last_baseline = block.bbox[3]
        if block_segments:
            candidate = _merge_segments(block_segments)
            if candidate and is_valid_title(candidate):
                return candidate

    # Fallback: look for centered text in first few lines
    if not page.lines:
        return None

    collected: List[str] = []
    org_tokens = {"society", "college", "association", "journal", "thoracic"}
    stop_prefixes = (
        "Official Journal",
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

    for raw_line in page.lines[:20]:
        if _should_skip_line(raw_line):
            continue
        line = raw_line
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

        if len(" ".join(collected)) > 260:
            break

    filtered: List[str] = []
    for segment in collected:
        lower = segment.lower()
        if not filtered and segment.isupper() and any(token in lower for token in org_tokens):
            continue
        filtered.append(segment)

    header_noise = set(HEADER_NOISE_TITLES)
    header_noise.update({"american thoracic society statement"})
    while filtered and filtered[0].strip().lower() in header_noise:
        filtered.pop(0)

    if filtered:
        title_segments: List[str] = []
        for segment in filtered:
            lower = segment.lower()
            if segment.isupper() and len(segment.split()) <= 4:
                break
            if re.search(r"^committee on", lower):
                break
            if "this official statement" in lower:
                break
            if segment.count(",") >= 3 and any(char.isupper() for char in segment):
                break
            title_segments.append(segment)
            if len(" ".join(title_segments)) > 240:
                break
        if title_segments:
            return _merge_segments(title_segments)

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

    for raw_line in page.lines[:3]:
        candidate = raw_line.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if any(pattern.search(candidate) for pattern in RUNNING_HEADER_PATTERNS):
            continue
        # Skip if it looks like metadata
        if any(
            kw in lowered
            for kw in ['page', 'copyright', '©', 'doi:', 'vol.', 'issue', 'received', 'accepted']
        ):
            continue
        if re.match(r"guideline\s+\d+", lowered):
            continue
        if len(candidate) > 10:
            return candidate

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

    heading_block = _collect_affiliation_text(pages[:2])
    first_page_text = '\n'.join(pages[0].lines)
    candidate_text = "\n".join(part for part in (first_page_text, heading_block) if part)

    # Extract affiliations (superscript numbers/letters)
    affiliations = extract_superscript_affiliations(candidate_text)

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
    def _strip_running_header(line: str) -> bool:
        cleaned = line.strip()
        if not cleaned:
            return True
        if any(pattern.search(cleaned) for pattern in RUNNING_HEADER_PATTERNS):
            return True
        lowered = cleaned.lower()
        if lowered.startswith(("guideline", "statement", "american thoracic society documents")):
            return True
        if cleaned.startswith("©") or "©" in cleaned:
            return True
        return False

    header_lines: List[str] = []
    for page in pages[:2]:
        for line in (page.lines or [])[:40]:
            cleaned = line.strip()
            if not cleaned:
                continue
            if _strip_running_header(line):
                continue
            if re.match(r"(abstract|summary|keywords)\b", cleaned, re.IGNORECASE):
                break
            header_lines.append(cleaned)
        if header_lines:
            break

    header_block = " ".join(header_lines)
    header_block = re.sub(r"\s+", " ", header_block)
    header_block = header_block.replace(" and ", ", ")
    header_block = AUTHOR_PREFIX_PATTERN.sub("", header_block)

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

    affiliation_block = _collect_affiliation_text(pages[:2])
    combined_affiliation_text = "\n".join(
        part
        for part in (
            "\n".join(first_page.lines[:120]),
            affiliation_block,
        )
        if part
    )
    all_affiliations_map = extract_superscript_affiliations(combined_affiliation_text)
    affiliation_entries = list(all_affiliations_map.items())

    authors: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for token in _tokenise_author_block(header_block):
        if not token:
            continue

        raw_markers, clean_token = _extract_author_markers(token)
        markers = [marker for marker in raw_markers if _valid_marker(marker)]

        if not _looks_like_name(clean_token):
            fallback = _extract_trailing_name(clean_token)
            if not fallback:
                continue
            clean_token = fallback

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
            _, clean_token = _extract_author_markers(token)
            if not _looks_like_name(clean_token):
                fallback = _extract_trailing_name(clean_token)
                if not fallback:
                    continue
                clean_token = fallback
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

    marker_to_id: Dict[str, str] = {}
    affiliation_records: List[Dict[str, str]] = []
    for marker, text in affiliation_entries:
        normalized = _normalize_marker(marker)
        if not normalized or not text:
            continue
        if normalized in marker_to_id:
            continue
        canonical_id = str(len(marker_to_id) + 1)
        marker_to_id[normalized] = canonical_id
        affiliation_records.append({"id": canonical_id, "text": text})

    if not marker_to_id and affiliation_entries and not affiliation_records:
        for idx, (marker, text) in enumerate(affiliation_entries, start=1):
            if not text:
                continue
            canonical_id = str(idx)
            normalized = _normalize_marker(marker)
            if normalized:
                marker_to_id[normalized] = canonical_id
            affiliation_records.append({"id": canonical_id, "text": text})

    if marker_to_id:
        for author in authors:
            raw_markers = author.get("footnotes", [])
            normalized_markers: List[str] = []
            extra_markers: List[str] = []
            for marker in raw_markers:
                normalized = _normalize_marker(marker)
                if normalized in marker_to_id:
                    normalized_markers.append(marker_to_id[normalized])
                else:
                    extra_markers.append(marker)
            author["footnotes"] = normalized_markers + extra_markers

    corresponding = extract_affiliations_and_correspondence(pages).get("corresponding_author")

    return {
        "authors": authors,
        "affiliations": affiliation_records,
        "corresponding_author": corresponding,
    }


def extract_superscript_affiliations(text: str) -> Dict[str, str]:
    """Extract affiliations mapped by superscript markers preserving order."""

    entries = OrderedDict()
    for marker, body in _parse_affiliation_entries(text):
        if not marker or not body:
            continue
        normalized_marker = marker.strip()
        if not _valid_marker(normalized_marker):
            continue
        entries.setdefault(normalized_marker, body)
    return entries


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


def link_authors_to_affiliations(
    authors: List["Author"],
    affiliations: List["Affiliation"],
    pages: List[PageData],
) -> List[str]:
    if not authors or not affiliations:
        return []
    if all(getattr(author, "affiliation_ids", []) for author in authors):
        return []

    window_lines: List[str] = []
    for page in pages[:2]:
        window_lines.extend(line for line in (page.lines or [])[:120] if line.strip())
    converted_lines = [line.translate(SUPERSCRIPT_TRANSLATION) for line in window_lines]

    alias_map: Dict[str, str] = {}
    for affiliation in affiliations:
        aff_id_raw = getattr(affiliation, "id", "") or ""
        aff_id = str(aff_id_raw)
        if not aff_id:
            continue
        alias_map[aff_id] = aff_id
        alias_map[aff_id.lower()] = aff_id
        digits = re.sub(r"[^0-9]", "", aff_id)
        if digits:
            alias_map[digits] = aff_id

    keyword_map: Dict[str, set[str]] = {}
    for affiliation in affiliations:
        aff_id = getattr(affiliation, "id", None)
        text = " ".join(
            part for part in [getattr(affiliation, "text", ""), getattr(affiliation, "institution", "")] if part
        )
        tokens = {token for token in re.findall(r"[A-Z]{3,}", text)}
        keyword_map[str(aff_id)] = tokens

    unresolved: List["Author"] = []

    for author in authors:
        current_ids = getattr(author, "affiliation_ids", None) or []
        if current_ids:
            continue
        assigned: List[str] = []
        family = (author.family or "").strip()
        if not family:
            unresolved.append(author)
            continue

        name_variants = [family]
        if author.given:
            name_variants.append(f"{author.given.strip()} {family}")

        for variant in name_variants:
            pattern_variant = variant.strip()
            if not pattern_variant:
                continue
            for line in converted_lines:
                if pattern_variant.lower() not in line.lower():
                    continue
                for alias, target in alias_map.items():
                    if not alias:
                        continue
                    marker_pattern = rf"{re.escape(pattern_variant)}\s*[,\[(\-]*\s*{re.escape(alias)}\b"
                    if re.search(marker_pattern, line, re.IGNORECASE):
                        if target not in assigned:
                            assigned.append(target)
                if assigned:
                    break
            if assigned:
                break

        if assigned:
            author.affiliation_ids = assigned
            continue

        line_match = next((line for line in converted_lines if family.lower() in line.lower()), "")
        line_upper = line_match.upper()
        matched_aff: Optional[str] = None
        if line_upper:
            for affiliation in affiliations:
                aff_id = getattr(affiliation, "id", None)
                if aff_id is None:
                    continue
                keywords = keyword_map.get(str(aff_id)) or set()
                if keywords and any(token in line_upper for token in keywords):
                    matched_aff = str(aff_id)
                    break

        if matched_aff:
            author.affiliation_ids = [matched_aff]
            continue

        unresolved.append(author)

    if unresolved and len(affiliations) == 1:
        fallback_id = str(getattr(affiliations[0], "id", ""))
        if fallback_id:
            for author in unresolved:
                author.affiliation_ids = [fallback_id]
            LOGGER.info(
                "Assigned all authors to sole affiliation id '%s' due to missing explicit markers.",
                fallback_id,
            )
        return []

    unresolved_names = [author.family or author.given or "?" for author in unresolved if author]
    coverage = 0.0
    if authors:
        mapped = sum(1 for author in authors if getattr(author, "affiliation_ids", []))
        coverage = mapped / len(authors)
    if unresolved_names and coverage < 0.6:
        LOGGER.warning(
            "Unable to resolve affiliations for authors: %s",
            ", ".join(unresolved_names),
        )
    return unresolved_names


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

    block = block.replace("·", ",").replace("•", ",")
    block = re.sub(
        r"\((?:MD|PhD|DO|MBA|MS|MSc|MPH|MBBS|FRCP|FRCPath|DDS|RN)[^)]*\)",
        "",
        block,
        flags=re.IGNORECASE,
    )
    block = AUTHOR_PREFIX_PATTERN.sub("", block)
    parts = re.split(r",\s*|\s+;\s*", block)
    return [part.strip() for part in parts if part.strip()]


def _extract_trailing_name(token: str) -> Optional[str]:
    """Extract trailing personal name from a mixed token."""

    if not token:
        return None
    pattern = re.compile(
        r"([A-Z][a-z]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z]+){1,3})(?:\s+(Jr|Sr|II|III|IV|V))?$"
    )
    match = pattern.search(token.strip())
    if not match:
        return None
    candidate = match.group(1)
    suffix = match.group(2)
    if suffix:
        candidate = f"{candidate} {suffix}"
    return candidate if _looks_like_name(candidate) else None


def _looks_like_name(token: str) -> bool:
    """Heuristic check that ``token`` appears to be a personal name."""

    if not token:
        return False
    token = token.strip()
    if ":" in token:
        return False
    if token.isupper():
        return False
    lowered = token.lower()
    if any(term in lowered for term in NAME_EXCLUSION_TERMS):
        return False
    if not AUTHOR_NAME_PATTERN.match(token):
        return False
    return True


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


def _parse_affiliation_entries(text: str) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    marker_pattern = re.compile(r"^\s*([0-9]{1,2}(?:\s*,\s*[0-9]{1,2})*|[A-Za-z]|[†‡*]+)[\s\.)-]*\s*(.*)$")
    lines = text.splitlines()
    current_markers: List[str] = []
    current_text: List[str] = []

    def _flush() -> None:
        if not current_markers or not current_text:
            return
        cleaned = _clean_affiliation_text(current_text)
        if not cleaned:
            return
        for marker in current_markers:
            entries.append((marker, cleaned))

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            _flush()
            current_markers = []
            current_text = []
            continue
        match = marker_pattern.match(stripped)
        if match:
            _flush()
            markers = _expand_markers(match.group(1))
            body = match.group(2).strip()
            if not body:
                continue
            current_markers = markers
            current_text = [body] if body else []
            continue
        if current_markers:
            if not _looks_like_affiliation_line(stripped):
                continue
            current_text.append(stripped)

    _flush()
    return entries


def _expand_markers(raw: str) -> List[str]:
    tokens = [token.strip() for token in re.split(r"[\s,]+", raw) if token.strip()]
    return tokens or [raw.strip()]


def _clean_affiliation_text(lines: List[str]) -> str:
    joined = " ".join(lines)
    joined = re.sub(r"\s+", " ", joined)
    return joined.strip(" ,;:.-")


def _normalize_marker(marker: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", marker.lower())


def _looks_like_affiliation_line(line: str) -> bool:
    if not line:
        return False
    lowered = line.lower()
    keywords = (
        "university",
        "hospital",
        "department",
        "division",
        "school",
        "institute",
        "center",
        "centre",
        "clinic",
        "medical",
        "pulmonology",
        "pathology",
        "medicine",
        "research",
    )
    if any(keyword in lowered for keyword in keywords):
        return True
    if re.search(r"\d", line) and "," in line:
        return True
    return False


def _extract_author_markers(token: str) -> Tuple[List[str], str]:
    markers: List[str] = []
    wrapped_pattern = re.compile(
        r"(?:(?<=\s)|(?<=,)|(?<=;)|(?<=\()|(?<=\[))(\d{1,2}|[a-z]|[†‡*])(?=(?:\s|,|;|\.|\)|\]|$))",
        re.IGNORECASE,
    )
    for match in wrapped_pattern.finditer(token):
        markers.append(match.group(1))
    tail_match = re.search(r"(\d{1,2}|[a-z]|[†‡*])$", token, re.IGNORECASE)
    if tail_match:
        markers.append(tail_match.group(1))

    # Deduplicate while preserving order
    seen_markers: set[str] = set()
    ordered_markers: List[str] = []
    for marker in markers:
        key = marker.lower()
        if key in seen_markers:
            continue
        seen_markers.add(key)
        ordered_markers.append(marker)

    cleaned = token
    for marker in ordered_markers:
        cleaned = re.sub(
            rf"(?i)(?:\s|,|;|\(|\[)+{re.escape(marker)}(?=(?:\s|,|;|\.|\)|\]|$))",
            " ",
            cleaned,
        )
        cleaned = re.sub(rf"(?i){re.escape(marker)}(?=$)", " ", cleaned)

    cleaned = re.sub(r"[†‡*]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:")
    return ordered_markers, cleaned


def _valid_marker(marker: str) -> bool:
    digits = "".join(ch for ch in marker if ch.isdigit())
    if digits:
        if len(digits) > 2:
            return False
        value = int(digits)
        if 1900 <= value <= 2100:
            return False
    return True


__all__ = [
    "extract_title_hierarchical",
    "is_valid_title",
    "extract_affiliations_and_correspondence",
    "extract_authors_affiliations",
    "extract_coi_and_funding",
    "extract_doi",
    "link_authors_to_affiliations",
]
