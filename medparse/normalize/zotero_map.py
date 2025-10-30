"""Lightweight Zotero front-matter lookup for article extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from medparse.normalize.fm_zotero import (
    ZoteroEntry,
    ZoteroIndex,
    load_zotero_library,
    make_title_signature,
)
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

_LIBRARY_PATH: Optional[Path] = None


@dataclass
class FrontMatterAuthor:
    given: str
    family: str
    affiliation: Optional[str] = None


@dataclass
class FrontMatter:
    title: Optional[str]
    doi: Optional[str]
    journal: Optional[str]
    year: Optional[int]
    authors: List[FrontMatterAuthor]
    affiliations: List[str]
    match_method: str
    match_score: float
    entry_id: Optional[str]
    raw: Dict[str, Any]


def configure_zotero_library(path: Optional[str]) -> None:
    """Configure the Zotero library path used for lookups."""

    global _LIBRARY_PATH
    _LIBRARY_PATH = Path(path) if path else None


def lookup_front_matter(doi: Optional[str], title: Optional[str]) -> Optional[FrontMatter]:
    """Return Zotero-derived front matter for ``doi``/``title`` if available."""

    index = _load_index()
    if not index:
        return None

    # DOI lookup takes precedence
    if doi:
        candidate = index.by_doi.get(doi.lower())
        if candidate:
            return _entry_to_front_matter(candidate, method="doi", score=1.0)

    if title:
        signature = make_title_signature(title)
        if signature:
            candidates = index.by_title_signature.get(signature, [])
            best_entry, best_score = _best_title_candidate(title, candidates)
            if best_entry and best_score >= 0.9:
                return _entry_to_front_matter(best_entry, method="title_signature", score=best_score)

        best_entry, best_score = _best_title_candidate(title, index.entries)
        if best_entry and best_score >= 0.88:
            return _entry_to_front_matter(best_entry, method="title_fuzzy", score=best_score)

    return None


def _load_index() -> Optional[ZoteroIndex]:
    if _LIBRARY_PATH is None:
        return None
    try:
        return load_zotero_library(str(_LIBRARY_PATH))
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.debug("Failed to load Zotero library at %s: %s", _LIBRARY_PATH, exc)
        return None


def _best_title_candidate(
    title: str,
    candidates: List[ZoteroEntry],
) -> Tuple[Optional[ZoteroEntry], float]:
    best: Optional[ZoteroEntry] = None
    best_score = 0.0
    if not title or not candidates:
        return best, best_score

    for entry in candidates:
        source_title = entry.title or ""
        if not source_title:
            continue
        score = fuzz.token_set_ratio(title, source_title) / 100.0
        if score > best_score:
            best_score = score
            best = entry
    return best, best_score


def _entry_to_front_matter(entry: ZoteroEntry, *, method: str, score: float) -> FrontMatter:
    record = entry.record

    doi = _coerce_str(record.get("DOI"))
    journal = _coerce_str(record.get("container-title"))
    authors_raw = record.get("author") or []
    authors: List[FrontMatterAuthor] = []
    affiliation_records: List[str] = []

    for author in authors_raw:
        if not isinstance(author, dict):
            continue
        given = _coerce_str(author.get("given")) or ""
        family = _coerce_str(author.get("family")) or ""
        if not (given or family):
            literal = _coerce_str(author.get("literal"))
            if literal:
                parts = literal.split()
                if len(parts) >= 2:
                    given = " ".join(parts[:-1])
                    family = parts[-1]
                else:
                    family = literal
        affiliation = _coerce_str(author.get("affiliation") or author.get("institution"))
        if affiliation:
            affiliation_records.append(affiliation)
        authors.append(FrontMatterAuthor(given=given, family=family, affiliation=affiliation))

    unique_affiliations = list(dict.fromkeys(text for text in affiliation_records if text))

    return FrontMatter(
        title=entry.title or _coerce_str(record.get("title")),
        doi=doi.lower() if doi else None,
        journal=journal,
        year=entry.year,
        authors=authors,
        affiliations=unique_affiliations,
        match_method=method,
        match_score=score,
        entry_id=_coerce_str(record.get("id")),
        raw=record,
    )


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return str(value).strip() or None


__all__ = [
    "FrontMatter",
    "FrontMatterAuthor",
    "configure_zotero_library",
    "lookup_front_matter",
]
