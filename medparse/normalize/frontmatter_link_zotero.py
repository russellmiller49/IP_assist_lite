"""Link extracted documents to Zotero CSL JSON front matter."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from rapidfuzz import fuzz

from medparse.schema.article import ArticleDocument, Author
from medparse.schema.textbook import AuthorInfo, BookMeta, TextbookChapterDocument
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}


@dataclass
class ZoteroEntry:
    record: Dict[str, Any]
    title: str
    title_signature: str
    container_signature: str
    year: Optional[int]
    doi: Optional[str]
    pmid: Optional[str]


@dataclass
class ZoteroIndex:
    entries: List[ZoteroEntry]
    by_doi: Dict[str, ZoteroEntry]
    by_pmid: Dict[str, ZoteroEntry]
    by_title_signature: Dict[str, List[ZoteroEntry]]
    by_year: Dict[int, List[ZoteroEntry]]


def make_title_signature(value: Optional[str]) -> str:
    """Normalize title text into a signature used for fuzzy matching."""

    if not value:
        return ""
    normalized = value.lower()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    tokens = [token for token in normalized.split() if token and token not in STOPWORDS]
    return " ".join(tokens)


def _extract_year(record: Dict[str, Any]) -> Optional[int]:
    issued = record.get("issued") or {}
    date_parts = issued.get("date-parts") or []
    if not date_parts:
        return None
    first = date_parts[0]
    if not first:
        return None
    try:
        return int(first[0])
    except (TypeError, ValueError, IndexError):
        return None


def _coerce_str(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _build_entry(record: Dict[str, Any]) -> ZoteroEntry:
    title = _coerce_str(record.get("title")) or ""
    container = _coerce_str(record.get("container-title")) or ""
    doi = _coerce_str(record.get("DOI"))
    pmid = _coerce_str(record.get("PMID")) or _coerce_str(record.get("pmid"))
    return ZoteroEntry(
        record=record,
        title=title,
        title_signature=make_title_signature(title),
        container_signature=make_title_signature(container),
        year=_extract_year(record),
        doi=doi.lower() if doi else None,
        pmid=pmid.lower() if pmid else None,
    )


@lru_cache(maxsize=8)
def load_zotero_library(path: Optional[str]) -> Optional[ZoteroIndex]:
    """Load the Zotero CSL JSON export and build lookup indices."""

    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        LOGGER.debug("Zotero library not found at %s", file_path)
        return None
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed to load Zotero library from %s: %s", file_path, exc)
        return None
    if not isinstance(payload, list):
        LOGGER.warning("Zotero library at %s is not a list; skipping.", file_path)
        return None

    entries: List[ZoteroEntry] = []
    by_doi: Dict[str, ZoteroEntry] = {}
    by_pmid: Dict[str, ZoteroEntry] = {}
    by_title_signature: Dict[str, List[ZoteroEntry]] = {}
    by_year: Dict[int, List[ZoteroEntry]] = {}

    for raw in payload:
        if not isinstance(raw, dict):
            continue
        entry = _build_entry(raw)
        entries.append(entry)
        if entry.doi:
            by_doi.setdefault(entry.doi, entry)
        if entry.pmid:
            by_pmid.setdefault(entry.pmid, entry)
        if entry.title_signature:
            by_title_signature.setdefault(entry.title_signature, []).append(entry)
        if entry.year is not None:
            by_year.setdefault(entry.year, []).append(entry)

    LOGGER.debug(
        "Loaded %d Zotero entries (doi=%d, pmid=%d) from %s",
        len(entries),
        len(by_doi),
        len(by_pmid),
        file_path,
    )
    return ZoteroIndex(
        entries=entries,
        by_doi=by_doi,
        by_pmid=by_pmid,
        by_title_signature=by_title_signature,
        by_year=by_year,
    )


def _fuzzy_best_match(
    doc_title: str,
    candidates: Iterable[ZoteroEntry],
) -> Tuple[Optional[ZoteroEntry], float]:
    best: Optional[ZoteroEntry] = None
    best_score = 0.0
    for entry in candidates:
        if not entry.title:
            continue
        score = fuzz.token_set_ratio(doc_title, entry.title) / 100.0
        if score > best_score:
            best_score = score
            best = entry
    return best, best_score


def _container_matches(
    doc_container_sig: Optional[str],
    entry_container_sig: str,
    min_ratio: float,
) -> bool:
    if not doc_container_sig or not entry_container_sig:
        return True
    score = fuzz.ratio(doc_container_sig, entry_container_sig) / 100.0
    return score >= min_ratio


def match_record(
    *,
    document_type: str,
    title: Optional[str],
    doi: Optional[str],
    pmid: Optional[str],
    year: Optional[int],
    container_title: Optional[str],
    index: Optional[ZoteroIndex],
    min_ratio: float,
    fallback_ratio: float,
) -> Tuple[Optional[ZoteroEntry], Optional[str], float]:
    """Match a document to a Zotero record."""

    if not index:
        return None, None, 0.0

    if doi:
        record = index.by_doi.get(doi.lower())
        if record:
            return record, "doi", 1.0

    if pmid:
        record = index.by_pmid.get(pmid.lower())
        if record:
            return record, "pmid", 1.0

    if not title:
        return None, None, 0.0

    doc_container_sig = make_title_signature(container_title)
    candidates: List[ZoteroEntry] = []
    if year is not None and year in index.by_year:
        candidates.extend(index.by_year[year])
    else:
        candidates = list(index.entries)

    best, score = _fuzzy_best_match(title, candidates)
    if best and score >= min_ratio:
        if _container_matches(doc_container_sig, best.container_signature, 0.85):
            return best, "title_year", score

    best, score = _fuzzy_best_match(title, index.entries)
    if best and score >= fallback_ratio:
        if _container_matches(doc_container_sig, best.container_signature, 0.85):
            return best, "title", score

    return None, None, 0.0


def _extract_author_list(record: Dict[str, Any]) -> List[Dict[str, str]]:
    authors = []
    for item in record.get("author", []) or []:
        if not isinstance(item, dict):
            continue
        if "literal" in item:
            literal = _coerce_str(item.get("literal"))
            if literal:
                authors.append({"given": "", "family": literal})
            continue
        given = _coerce_str(item.get("given")) or ""
        family = _coerce_str(item.get("family")) or ""
        if not (given or family):
            continue
        authors.append({"given": given, "family": family})
    return authors


def enrich_article(
    document: ArticleDocument,
    entry: ZoteroEntry,
    method: str,
    score: float,
    prefer_doi: bool = True,
) -> None:
    record = entry.record
    doi = _coerce_str(record.get("DOI"))
    if doi and (prefer_doi or not document.doi):
        document.doi = doi

    pmid = _coerce_str(record.get("PMID")) or _coerce_str(record.get("pmid"))
    if pmid and not document.pmid:
        document.pmid = pmid

    title = _coerce_str(record.get("title"))
    if title and (not document.title or method in {"doi", "pmid"}):
        document.title = title
        document.title_source = "zotero"

    container = _coerce_str(record.get("container-title"))
    if container:
        document.journal = container

    issn = record.get("ISSN")
    if issn:
        if isinstance(issn, list):
            document.issn = ", ".join(str(item) for item in issn if item)
        else:
            document.issn = str(issn)

    document.volume = _coerce_str(record.get("volume")) or document.volume
    document.issue = _coerce_str(record.get("issue")) or document.issue
    document.pages = _coerce_str(record.get("page")) or document.pages

    if entry.year:
        document.year = entry.year

    url = _coerce_str(record.get("URL"))
    if url:
        document.url = url

    authors = _extract_author_list(record)
    if authors:
        document.authors = [
            Author(
                given=author.get("given", ""),
                family=author.get("family", ""),
            )
            for author in authors
        ]


def _ensure_book_meta(document: TextbookChapterDocument) -> BookMeta:
    if document.book_meta is None:
        document.book_meta = BookMeta(
            book_title="",
            editors=[],
        )
    return document.book_meta


def enrich_textbook(
    document: TextbookChapterDocument,
    entry: ZoteroEntry,
    method: str,
    score: float,
) -> None:
    record = entry.record
    title = _coerce_str(record.get("title"))
    if title and (not document.chapter_title or method in {"doi", "pmid"}):
        document.chapter_title = title

    doi = _coerce_str(record.get("DOI"))
    if doi and (not document.chapter_doi or method in {"doi", "pmid"}):
        document.chapter_doi = doi

    authors = _extract_author_list(record)
    if authors:
        document.chapter_authors = [
            AuthorInfo(name=" ".join(part for part in (author.get("given"), author.get("family")) if part))
            for author in authors
            if author.get("given") or author.get("family")
        ]

    container = _coerce_str(record.get("container-title"))
    book_meta = _ensure_book_meta(document)
    if container:
        book_meta.book_title = container
    if entry.year:
        book_meta.year = entry.year
    if record.get("ISBN"):
        isbn = record.get("ISBN")
        if isinstance(isbn, list):
            book_meta.isbn = ", ".join(str(item) for item in isbn if item)
        else:
            book_meta.isbn = str(isbn)


def _compute_confidence(method: Optional[str], score: float) -> float:
    if method in {"doi", "pmid"}:
        return 1.0
    return max(0.85, score)


def link_front_matter(
    document: Union[ArticleDocument, TextbookChapterDocument],
    zotero_path: Optional[str],
    enrichment_settings: Optional[Union[Dict[str, Any], Any]] = None,
) -> Tuple[Union[ArticleDocument, TextbookChapterDocument], Dict[str, Any]]:
    """Link document front matter to a Zotero library if possible."""

    settings = enrichment_settings or {}
    if hasattr(settings, "get"):
        get_setting = settings.get  # type: ignore[attr-defined]
    else:  # pragma: no cover - defensive
        def get_setting(key: str, default: Any = None) -> Any:
            return default

    min_ratio = float(get_setting("min_title_match", 0.90))
    fallback_ratio = max(float(get_setting("fallback_title_match", 0.92)), min_ratio + 0.02)
    prefer_doi = bool(get_setting("prefer_doi", True))

    index = load_zotero_library(zotero_path)
    if not index:
        return document, {"status": "library_unavailable", "source": "zotero"}

    doc_type = getattr(document, "doc_type", "")
    if doc_type == "article":
        title = document.title
        doi = document.doi
        pmid = document.pmid
        year = document.year
        container = document.journal
    elif doc_type == "textbook_chapter":
        title = document.chapter_title
        doi = document.chapter_doi
        pmid = None
        book_meta = document.book_meta
        year = book_meta.year if book_meta else None
        container = book_meta.book_title if book_meta else None
    else:
        return document, {"status": "unsupported_doc_type", "source": "zotero"}

    entry, method, score = match_record(
        document_type=doc_type,
        title=title,
        doi=doi,
        pmid=pmid,
        year=year,
        container_title=container,
        index=index,
        min_ratio=min_ratio,
        fallback_ratio=fallback_ratio,
    )

    if not entry:
        return document, {"status": "not_found", "source": "zotero"}

    if doc_type == "article":
        enrich_article(document, entry, method, score, prefer_doi=prefer_doi)
    elif doc_type == "textbook_chapter":
        enrich_textbook(document, entry, method, score)

    confidence = _compute_confidence(method, score)
    document.front_matter_source = "zotero"
    document.front_matter_confidence = confidence

    fm_info = {
        "status": "linked",
        "source": "zotero",
        "method": method,
        "score": score,
        "confidence": confidence,
        "id": entry.record.get("id"),
    }
    return document, fm_info


__all__ = [
    "link_front_matter",
    "load_zotero_library",
    "make_title_signature",
]
