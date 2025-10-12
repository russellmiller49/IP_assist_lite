"""Reference parsing utilities and gating rules."""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

from medparse.ingest.layout import collect_sections, iter_section_text
from medparse.ingest.pdf_reader import PageContent

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
PMID_RE = re.compile(r"\bPMID:\s*\d{7,8}\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
IMPERATIVES = {"install", "connect", "tap", "insert", "raise", "lubricate", "retract", "press"}
JOURNAL_PATTERN = re.compile(r"\d+\(\d+\):\d+-\d+")


def looks_like_bibliography_line(line: str) -> bool:
    """Return True when the supplied line resembles a bibliographic entry."""
    if DOI_RE.search(line) or PMID_RE.search(line):
        return True

    words = line.lower().split()
    if words and words[0] in IMPERATIVES:
        return False

    if JOURNAL_PATTERN.search(line):
        return True

    year_match = YEAR_RE.search(line)
    if year_match and 1950 <= int(year_match.group()) <= 2035:
        if any(token in line for token in (".", ",", ";")):
            return True

    return False


def extract_references(pages: Sequence[PageContent]) -> List[str]:
    """Collect gated reference lines from the pages."""
    candidates: List[str] = []

    sections = collect_sections(pages)
    if sections:
        next_titles = [section.title for section in sections if section.title.lower() != "references"]
        section_lines = iter_section_text(pages, sections, "References", next_titles)

        for _, line in section_lines:
            cleaned = line.strip()
            if not cleaned:
                continue
            if looks_like_bibliography_line(cleaned):
                candidates.append(cleaned)

    # Allow DOI/PMID hits outside the references section
    if not candidates:
        for page in pages:
            for line in page.lines:
                cleaned = line.strip()
                if not cleaned:
                    continue
                if DOI_RE.search(cleaned) or PMID_RE.search(cleaned):
                    candidates.append(cleaned)

    return candidates
