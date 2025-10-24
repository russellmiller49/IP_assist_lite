"""Metadata normalization helpers for different document types."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
PART_NUMBER_RE = re.compile(r"\bpn\s*([A-Z0-9\-]+)\b", re.IGNORECASE)
REVISION_RE = re.compile(r"\brev(?:ision)?\s*([A-Z0-9.]+)\b", re.IGNORECASE)
PUB_DATE_RE = re.compile(r"(20\d{2})[./-](0[1-9]|1[0-2])")
MODEL_RE = re.compile(r"\bmodel\s*([A-Z0-9\-]+)\b", re.IGNORECASE)
SOFTWARE_RE = re.compile(r"\b([A-Za-z]+(?:\s+OS\d?)?)\s*v(?:ersion)?\s*([0-9.]+)\b", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^chapter\s*(\d+[A-Za-z]?)[:\-\s]*", re.IGNORECASE)


def extract_ifu_front_matter(lines: Iterable[str]) -> dict:
    """Return IFU front-matter metadata from the first few pages."""

    metadata = {
        "part_number": None,
        "revision": None,
        "publication_date": None,
        "model": None,
        "software_versions": [],
    }
    software_versions: List[str] = []

    for line in lines:
        lowered = line.lower()
        if metadata["part_number"] is None:
            match = PART_NUMBER_RE.search(lowered)
            if match:
                metadata["part_number"] = match.group(1).upper()

        if metadata["revision"] is None:
            match = REVISION_RE.search(lowered)
            if match:
                metadata["revision"] = match.group(1).upper()

        if metadata["publication_date"] is None:
            match = PUB_DATE_RE.search(lowered.replace(" ", ""))
            if match:
                metadata["publication_date"] = f"{match.group(1)}-{match.group(2)}"

        if metadata["model"] is None:
            match = MODEL_RE.search(lowered)
            if match:
                metadata["model"] = match.group(1).upper()

        for soft_match in SOFTWARE_RE.finditer(line):
            software_name = soft_match.group(1).strip()
            version = soft_match.group(2).strip()
            software_versions.append(f"{software_name} v{version}")

    if software_versions:
        metadata["software_versions"] = sorted(set(software_versions))

    return metadata


def normalize_article_metadata(title: Optional[str], imprint_lines: Sequence[str]) -> dict:
    """Ensure essential article metadata such as year is captured."""

    metadata = {"title": title, "year": None}
    for line in imprint_lines:
        match = YEAR_RE.search(line)
        if match:
            metadata["year"] = int(match.group(0))
            break
    return metadata


def normalize_chapter_title(raw_title: str) -> Tuple[str, Optional[str]]:
    """Extract chapter number and clean title from a raw heading."""

    match = CHAPTER_RE.match(raw_title.strip())
    chapter_number = match.group(1) if match else None
    title = CHAPTER_RE.sub("", raw_title).strip()
    if title and title[0] == ":":
        title = title[1:].strip()
    return title, chapter_number


def normalize_authors(authors: Iterable[str]) -> List[str]:
    """Clean and deduplicate author names."""

    cleaned: List[str] = []
    seen: set[str] = set()
    for author in authors:
        for fragment in re.split(r"[;|]", author):
            candidate = fragment.strip()
            if not candidate:
                continue
            candidate = re.sub(r"\s+", " ", candidate)
            if candidate.lower() in seen:
                continue
            seen.add(candidate.lower())
            cleaned.append(candidate)
    return cleaned


__all__ = [
    "extract_ifu_front_matter",
    "normalize_article_metadata",
    "normalize_chapter_title",
    "normalize_authors",
]
