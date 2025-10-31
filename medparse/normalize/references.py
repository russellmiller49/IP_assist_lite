"""Reference normalization and gating logic."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Literal, Sequence, Tuple

from medparse.utils.text import collapse_whitespace

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s;]+", re.IGNORECASE)
PMID_RE = re.compile(r"\bpmid[:\s]*(\d+)\b", re.IGNORECASE)
JOURNAL_HINT_RE = re.compile(
    r"\b(journal|med(?:icine)?|respir|chest|ann(?:als)?|lung|thorac|bronch)\b", re.IGNORECASE
)
ANCHOR_TOKENS = {"references", "bibliography"}
ALLOWLIST_PATTERNS = (DOI_RE, PMID_RE, YEAR_RE, JOURNAL_HINT_RE)


def normalize_references(
    lines: Iterable[str],
    *,
    mode: Literal["article", "ifu", "textbook"],
    headings: Sequence[str] | None = None,
) -> List[str]:
    """Normalize reference strings respecting mode-specific gating rules."""

    assembled = [_normalize_reference_text(entry) for entry in _assemble_references(lines)]
    normalized_candidates = [entry for entry in assembled if entry]
    if not normalized_candidates:
        return []

    headings_lower = {heading.lower() for heading in (headings or [])}
    if mode == "ifu":
        if not _has_anchor(headings_lower):
            return []
        allowlisted = [line for line in normalized_candidates if _matches_allowlist(line)]
        if len(allowlisted) < 3:
            return []
        normalized_candidates = allowlisted

    seen: set[Tuple[str, str]] = set()
    results: List[str] = []
    for candidate in normalized_candidates:
        key = _reference_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        results.append(candidate)
    return [_build_reference_payload(text) for text in results]


def _prepare_line(line: str) -> str:
    return collapse_whitespace(line.strip())


def _normalize_reference_text(text: str) -> str:
    normalized = collapse_whitespace(text.strip())
    return normalized


def _assemble_references(lines: Iterable[str]) -> List[str]:
    entries: List[str] = []
    buffer = ""
    for raw in lines:
        line = _prepare_line(raw)
        if not line:
            continue
        if buffer:
            buffer = f"{buffer} {line}".strip()
        else:
            buffer = line
        if _is_reference_terminal(buffer):
            entries.append(buffer)
            buffer = ""
    if buffer:
        entries.append(buffer)
    return entries


def _is_reference_terminal(text: str) -> bool:
    if DOI_RE.search(text) or PMID_RE.search(text):
        return True
    if re.search(r"[:;]\s*\d", text):
        return True
    return bool(re.search(r"[.!?]\s*$", text))


def _has_anchor(headings: set[str]) -> bool:
    return any(anchor in headings for anchor in ANCHOR_TOKENS)


def _matches_allowlist(text: str) -> bool:
    return any(pattern.search(text) for pattern in ALLOWLIST_PATTERNS)


def _reference_key(text: str) -> Tuple[str, str]:
    doi = _extract_doi(text)
    if doi:
        return ("doi", doi.lower())

    first_author = _first_author(text)
    year = _extract_year(text)
    title = _extract_title(text)

    if first_author and year and title:
        normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        return ("meta", f"{first_author.lower()}|{year}|{normalized_title}")

    return ("raw", re.sub(r"\s+", " ", text.lower()))


def _extract_doi(text: str) -> str | None:
    match = DOI_RE.search(text)
    return match.group(0) if match else None


def _extract_pmid(text: str) -> str | None:
    match = PMID_RE.search(text)
    return match.group(1) if match else None


def _extract_year(text: str) -> str | None:
    match = YEAR_RE.search(text)
    return match.group(0) if match else None


def _first_author(text: str) -> str | None:
    # Accept "Surname, Initials" or "Surname Initials" forms.
    match = re.match(r"([A-Z][A-Za-z'\- ]+?)(?:,|\s)", text)
    return match.group(1).strip() if match else None


def _extract_title(text: str) -> str | None:
    # Look for quoted titles or the segment after the author list.
    quoted = re.search(r"[\"“](.+?)[\"”]", text)
    if quoted:
        return quoted.group(1)

    segments = [seg.strip() for seg in text.split(".") if seg.strip()]
    if len(segments) >= 2:
        candidate = segments[1]
        if len(candidate) >= 4:
            return candidate
    return None


def _extract_journal(text: str) -> str | None:
    match = re.search(r"\.\s*([A-Z][^.;]+?)\s+(?:19|20)\d{2}", text)
    if match:
        return match.group(1).strip()
    return None


def _build_reference_payload(text: str) -> Dict[str, object]:
    payload: Dict[str, object] = {"text": text}
    doi = _extract_doi(text)
    if doi:
        payload["doi"] = doi
    pmid = _extract_pmid(text)
    if pmid:
        payload["pmid"] = pmid
    year = _extract_year(text)
    if year:
        payload["year"] = year
    journal = _extract_journal(text)
    if journal:
        payload["journal"] = journal
    return payload


def is_true_bibliography(pages_text: Sequence[str]) -> bool:
    document = "\n".join(pages_text)
    if not re.search(r"\b(References|Bibliography)\b", document, re.IGNORECASE):
        return False
    hits = (
        len(DOI_RE.findall(document))
        + len(PMID_RE.findall(document))
        + len(JOURNAL_HINT_RE.findall(document))
    )
    return hits >= 3


def gate_ifu_references(ifu_json: dict, pages_text: Sequence[str]) -> None:
    """Gate IFU references based on bibliography detection.

    Sets references to empty list if no true bibliography is detected.
    This ensures validator warnings are suppressed for IFUs without bibliographies.

    Args:
        ifu_json: Dictionary with document fields (mutated in-place)
        pages_text: Full page text for bibliography detection
    """
    if not is_true_bibliography(pages_text):
        ifu_json["references"] = []


__all__ = ["normalize_references", "is_true_bibliography", "gate_ifu_references"]
