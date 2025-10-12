"""Extractor for guideline documents."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from medparse.config import ExtractionConfig
from medparse.ingest.layout import build_sections
from medparse.ingest.pdf_reader import PageContent, iter_pages
from medparse.normalize.recommendations import normalize_recommendations
from medparse.types.base import EvidenceSpan
from medparse.types.guideline import GuidelineDocument, GuidelineRecommendation

RECOMMENDATION_HEADINGS = {"recommendations"}
SECTION_END_TITLES = {"references", "bibliography", "appendix", "acknowledgements"}
CONNECTOR_WORDS = {
    "of",
    "the",
    "and",
    "in",
    "for",
    "to",
    "with",
    "by",
    "on",
    "or",
    "vs",
    "per",
}

NUMBERED_ANCHOR_RE = re.compile(
    r"^(?:Recommendation\s*)?\(?(?P<number>\d{1,3})\)?[.)]?\s*(?P<rest>.*)"
)
SENTENCE_ANCHOR_RE = re.compile(
    r"^(?:For\s+.*?\b(?:recommend|suggest)\b|In patients\s+.*?\b(?:recommend|suggest)\b)",
    re.IGNORECASE,
)
RECOMMENDATION_VERB_RE = re.compile(
    r"\b(recommend(?:ation|ed)?|suggest(?:ed)?)\b", re.IGNORECASE
)
FIGURE_INLINE_RE = re.compile(
    r"[\[(]\s*(?P<label>(?:[●•\"“”'\s]*)(?:Fig(?:ure)?\.?)\s*[^)\]]*)[\])]",
    re.IGNORECASE,
)
GRADE_TOKEN_RE = re.compile(r"\b(GRADE|SIGN|ACCP)\s*([A-Z0-9/+-]+)", re.IGNORECASE)
GRADE_PAREN_RE = re.compile(
    r"\(\s*(?:Recommendation\s+)?(?:(GRADE|SIGN|ACCP)\s+)?grade\s*([A-Z0-9/+-]+)\s*\)",
    re.IGNORECASE,
)
GRADE_INLINE_RE = re.compile(r"Recommendation\s+grade\s+[A-Z0-9/+-]+", re.IGNORECASE)
CONSENSUS_RE = re.compile(r"(\d{1,3})\s*%\s*(consensus|agreement|in favor)", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

FOOTER_SUBSTRINGS = (
    "this document was downloaded",
    "unauthorized distribution is strictly prohibited",
    "vilmann peter",
    "georg thieme verlag",
    "endoscopy 2015",
)
NOISE_LINES = {
    "recommendations are shown with a green background.",
    "!",
}
MAX_RECOMMENDATION_NUMBER = 40


@dataclass(slots=True)
class _RecommendationCandidate:
    number: Optional[str]
    lines: List[str]
    page: int
    first_line: Optional[str] = None

    def text(self) -> str:
        return " ".join(self.lines).strip()


def extract_guideline(
    pdf_path: Path, config: Optional[ExtractionConfig] = None
) -> GuidelineDocument:
    """Extract structured guideline data."""
    config = config or ExtractionConfig()
    pages = list(iter_pages(pdf_path))
    raw_payloads = _extract_recommendations(pages)
    normalized_payloads = normalize_recommendations(raw_payloads)
    recommendations = [GuidelineRecommendation(**payload) for payload in normalized_payloads]

    document = GuidelineDocument(
        doc_type="guideline",
        source_file=str(pdf_path),
        page_count=len(pages),
        society=_find_society(pages),
        title=_extract_title(pages),
        year=_infer_year(pages),
        recommendations=recommendations,
    )
    document.sections = build_sections(document, pages)

    if config.fail_fast and not document.recommendations:
        raise ValueError("No guideline recommendations detected.")

    return document


def _extract_title(pages: Sequence[PageContent]) -> Optional[str]:
    if not pages:
        return None
    candidate_blocks = [block for block in pages[0].blocks if block.font_size]
    if candidate_blocks:
        block = max(candidate_blocks, key=lambda b: b.font_size)
        return block.text.strip()
    if pages[0].lines:
        return pages[0].lines[0].strip()
    return None


def _find_society(pages: Sequence[PageContent]) -> Optional[str]:
    if not pages:
        return None
    first_lines = pages[0].lines[:40]
    text = " ".join(first_lines)
    abbreviations = re.findall(r"\(([A-Z]{2,})\)", text)
    if abbreviations:
        unique = list(dict.fromkeys(abbreviations))[:3]
        return "/".join(unique)
    for line in pages[0].lines:
        if "society" in line.lower():
            return line.strip()
    return None


def _infer_year(pages: Sequence[PageContent]) -> Optional[int]:
    for page in pages:
        for line in page.lines:
            match = YEAR_RE.search(line)
            if match:
                return int(match.group())
    return None


def _extract_recommendations(pages: Sequence[PageContent]) -> List[dict]:
    candidates = _collect_candidates(pages)
    selected = _select_candidates(candidates)
    payloads: List[dict] = []
    for candidate in selected:
        payload = _build_recommendation(candidate, pages)
        if payload:
            payloads.append(payload)
    return payloads


def _collect_candidates(pages: Sequence[PageContent]) -> List[_RecommendationCandidate]:
    candidates: List[_RecommendationCandidate] = []
    inside = False
    current: Optional[_RecommendationCandidate] = None

    for page in pages:
        for raw_line in page.lines:
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered in RECOMMENDATION_HEADINGS:
                if current and current.lines:
                    candidates.append(current)
                current = None
                inside = True
                continue
            if lowered in SECTION_END_TITLES:
                if current and current.lines:
                    candidates.append(current)
                current = None
                inside = False
                continue
            if not inside:
                continue

            if _is_footer_line(line):
                if current and current.lines:
                    candidates.append(current)
                current = None
                continue

            number_match = _match_numbered_start(line)
            if number_match:
                if current and current.lines:
                    candidates.append(current)
                number, remainder = number_match
                current = _RecommendationCandidate(
                    number=number,
                    lines=[remainder] if remainder else [],
                    page=page.number,
                    first_line=remainder or None,
                )
                continue

            if _is_section_header(line):
                if current and current.lines:
                    candidates.append(current)
                current = None
                continue

            if lowered in NOISE_LINES:
                continue

            if _matches_sentence_anchor(line) and current is None:
                current = _RecommendationCandidate(
                    number=None,
                    lines=[line],
                    page=page.number,
                    first_line=line,
                )
                continue

            if current is None:
                continue

            if not current.first_line and line:
                current.first_line = line
            current.lines.append(line)

    if current and current.lines:
        candidates.append(current)
    return candidates


def _select_candidates(candidates: Sequence[_RecommendationCandidate]) -> List[_RecommendationCandidate]:
    grouped: dict[str, List[_RecommendationCandidate]] = defaultdict(list)
    unnumbered: List[_RecommendationCandidate] = []
    for candidate in candidates:
        if not candidate.lines:
            continue
        if candidate.number and candidate.number.isdigit():
            if int(candidate.number) > MAX_RECOMMENDATION_NUMBER:
                continue
            grouped[candidate.number].append(candidate)
        else:
            unnumbered.append(candidate)

    selected: List[_RecommendationCandidate] = []
    for number, items in grouped.items():
        filtered = [item for item in items if _is_recommendation_like(item)]
        if not filtered:
            continue
        best = max(filtered, key=_candidate_score)
        best.number = number
        selected.append(best)

    selected.sort(
        key=lambda cand: int(cand.number) if cand.number and cand.number.isdigit() else 0
    )
    selected.extend(candidate for candidate in unnumbered if _is_recommendation_like(candidate))
    return selected


def _build_recommendation(
    candidate: _RecommendationCandidate, pages: Sequence[PageContent]
) -> Optional[dict]:
    raw_text = candidate.text()
    if not raw_text:
        return None

    normalized_text = _normalize_text(raw_text)
    grade, strength_scale, text_without_grade = _extract_grade_from_text(normalized_text)
    cleaned_text, figures = _clean_recommendation_text(text_without_grade)
    if not cleaned_text:
        return None

    consensus = _extract_consensus(normalized_text)
    evidence = _find_evidence_span(pages, candidate.first_line or cleaned_text)

    return {
        "number": candidate.number,
        "text": cleaned_text,
        "grade": grade,
        "strength_scale": strength_scale,
        "consensus_percentage": consensus,
        "figures": figures,
        "evidence": evidence,
    }


def _extract_grade_from_text(text: str) -> Tuple[Optional[str], Optional[str], str]:
    working = text
    grade: Optional[str] = None
    strength_scale: Optional[str] = None

    for match in GRADE_PAREN_RE.finditer(text):
        if grade is None:
            grade = match.group(2).upper()
            strength_scale = match.group(1).upper() if match.group(1) else "GRADE"
        working = working.replace(match.group(0), " ")

    for match in GRADE_TOKEN_RE.finditer(text):
        if grade is None:
            grade = match.group(2).upper()
            strength_scale = match.group(1).upper()
        working = working.replace(match.group(0), " ")

    working = GRADE_INLINE_RE.sub(" ", working)
    cleaned = _normalize_whitespace(working)
    return grade, strength_scale, cleaned


def _clean_recommendation_text(text: str) -> Tuple[str, List[str]]:
    figures: List[str] = []
    working = text.strip()

    def _strip_label(match: re.Match[str]) -> str:
        raw_label = match.group("label")
        cleaned = re.sub(r'[\"“”\'●•]', "", raw_label)
        parts = [part.strip() for part in re.split(r"\s*,\s*", cleaned) if part.strip()]
        figures.extend(parts)
        return " "

    working = FIGURE_INLINE_RE.sub(_strip_label, working)
    working = working.strip('"\'“”‘’')
    normalized = _normalize_whitespace(working)
    return normalized, figures


def _extract_consensus(text: str) -> Optional[float]:
    match = CONSENSUS_RE.search(text)
    if match:
        return float(match.group(1))
    return None


def _find_evidence_span(pages: Sequence[PageContent], snippet: str) -> EvidenceSpan:
    normalized_snippet = _normalize_text(snippet).lower()[:80]
    for page in pages:
        normalized_page = _normalize_text(page.text).lower()
        if normalized_snippet and normalized_snippet in normalized_page:
            return EvidenceSpan(text=snippet.strip(), page=page.number)
    fallback_page = pages[0].number if pages else 1
    return EvidenceSpan(text=snippet.strip(), page=fallback_page)


def _match_numbered_start(line: str) -> Optional[Tuple[str, str]]:
    match = NUMBERED_ANCHOR_RE.match(line)
    if not match:
        return None
    number = match.group("number")
    rest = match.group("rest").strip()
    if number and not number.isdigit():
        return None
    return number, rest


def _matches_sentence_anchor(line: str) -> bool:
    merged = _remove_line_hyphenation(line)
    return bool(SENTENCE_ANCHOR_RE.match(merged))


def _is_section_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.isdigit():
        return False
    if stripped.lower() in RECOMMENDATION_HEADINGS:
        return False
    if not any(char.isalpha() for char in stripped):
        return False
    if any(char.isdigit() for char in stripped):
        return False
    if stripped.endswith((".", "?", "!", ":")):
        return False
    words = stripped.split()
    if len(words) > 10:
        return False
    lower_allowed = 0
    for word in words:
        cleaned = word.strip("()[]")
        if not cleaned:
            continue
        if cleaned.lower() in CONNECTOR_WORDS:
            continue
        if cleaned.isupper() or (cleaned[0].isupper() and cleaned[1:].islower()):
            continue
        lower_allowed += 1
    return lower_allowed <= 1


def _is_footer_line(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in FOOTER_SUBSTRINGS)


def _is_recommendation_like(candidate: _RecommendationCandidate) -> bool:
    normalized = _normalize_text(candidate.text()).lower()
    return bool(RECOMMENDATION_VERB_RE.search(normalized))


def _candidate_score(candidate: _RecommendationCandidate) -> int:
    normalized = _normalize_text(candidate.text()).lower()
    score = len(normalized)
    if "recommendation grade" in normalized:
        score += 20
    if RECOMMENDATION_VERB_RE.search(normalized):
        score += 100
    return score


def _normalize_text(value: str) -> str:
    merged = _remove_line_hyphenation(value)
    return _normalize_whitespace(merged)


def _remove_line_hyphenation(value: str) -> str:
    without_breaks = re.sub(r"(\w)-\s+(\w)", r"\1\2", value)
    return re.sub(r"-\s+([A-Za-z])", r"-\1", without_breaks)


def _normalize_whitespace(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\s+([.,;:])", r"\1", collapsed)
