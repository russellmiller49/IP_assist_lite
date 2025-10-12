"""Layout analysis helpers (headings, sections)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

from medparse.ingest.pdf_reader import PageContent
from medparse.ingest.cleaning import normalize_text_artifacts
from medparse.types.base import BaseDocument, EvidenceSpan, Section as SectionModel

HEADING_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s/&,-]{2,}$")
LEADING_SYMBOLS_RE = re.compile(r"^[\dA-Z][\dA-Z.\-\s]{0,4}\s+")
CALLOUT_RE = re.compile(
    r"^(?:box\s*\d+[A-Za-z]?|table\s*\d+[A-Za-z]?|fig(?:ure)?\.?\s*\d+[A-Za-z]?|!+|warning|caution|note)\b",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"^([-•●◦*]\s+|\d+\.\s+)")


@dataclass(slots=True)
class SectionBoundary:
    """Represents the start position of a detected section or callout heading."""

    title: str
    page: int
    line_index: int
    level: Optional[int] = None
    kind: Literal["section", "callout"] = "section"


def detect_headings(page: PageContent) -> List[SectionBoundary]:
    """Return headings detected within a page."""
    headings: List[SectionBoundary] = []
    font_sizes = [block.font_size for block in page.blocks if block.font_size]
    if not font_sizes:
        return _detect_headings_without_font(page)

    base_size = median(font_sizes)
    high_size = max(base_size + 1.5, sorted(font_sizes)[int(len(font_sizes) * 0.75)])
    seen: set[tuple[int, int, str]] = set()

    for block in page.blocks:
        if not block.text:
            continue
        title = _normalize_heading(block.text)
        if not title:
            continue
        if not block.font_size:
            continue

        is_large_text = block.font_size >= high_size
        looks_prominent = (
            block.is_bold and block.font_size >= base_size
        ) or is_large_text or _looks_like_heading(title)
        if not looks_prominent:
            continue

        line_index = _find_line_index(page.lines, title)
        if line_index is None:
            continue
        key = (page.number, line_index, title.lower())
        kind = _classify_boundary_kind(title)
        level = _infer_heading_level(block.font_size or base_size, base_size)
        if kind == "callout" and len(title) <= 2:
            level = None

        if key in seen and kind == "section":
            continue
        seen.add(key)
        headings.append(
            SectionBoundary(
                title=title,
                page=page.number,
                line_index=line_index,
                level=level,
                kind=kind,
            )
        )

    seen_positions = {(boundary.page, boundary.line_index) for boundary in headings}

    for idx, raw_line in enumerate(page.lines):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if (page.number, idx) in seen_positions:
            continue
        if CALLOUT_RE.match(stripped.lower()):
            headings.append(
                SectionBoundary(
                    title=stripped,
                    page=page.number,
                    line_index=idx,
                    level=None,
                    kind="callout",
                )
            )
            seen_positions.add((page.number, idx))

    return headings


def _normalize_heading(text: str) -> Optional[str]:
    cleaned = LEADING_SYMBOLS_RE.sub("", text.strip()).strip(": ").strip()
    if not cleaned:
        return None
    if sum(char.isalpha() for char in cleaned) < 4:
        return None
    lowered = cleaned.lower()
    if any(token in lowered for token in ("©", "http", "www.", "phone:", "@")):
        return None
    if cleaned.isdigit():
        return None
    return cleaned


def _classify_boundary_kind(title: str) -> Literal["section", "callout"]:
    normalized = title.strip().lower()
    if CALLOUT_RE.match(normalized):
        return "callout"
    if normalized in {"!", "⚠", "⚠️"}:
        return "callout"
    if len(normalized) <= 2 and not normalized.isalpha():
        return "callout"
    return "section"


def _infer_heading_level(font_size: float, base_size: float) -> Optional[int]:
    if font_size <= 0 or base_size <= 0:
        return None
    if font_size >= base_size * 1.6:
        return 1
    if font_size >= base_size * 1.3:
        return 2
    if font_size >= base_size * 1.1:
        return 3
    return 4


def _detect_headings_without_font(page: PageContent) -> List[SectionBoundary]:
    headings: List[SectionBoundary] = []
    seen: set[Tuple[int, int, str]] = set()

    for idx, raw_line in enumerate(page.lines):
        candidate = _normalize_heading(raw_line)
        if not candidate:
            continue
        if not _looks_like_heading(candidate):
            continue
        kind = _classify_boundary_kind(candidate)
        key = (page.number, idx, candidate.lower())
        if key in seen and kind == "section":
            continue
        seen.add(key)
        headings.append(
            SectionBoundary(
                title=candidate,
                page=page.number,
                line_index=idx,
                level=None,
                kind=kind,
            )
        )

    return headings


def _looks_like_heading(text: str) -> bool:
    words = text.split()
    if len(words) <= 1:
        solo = words[0] if words else ""
        if len(solo) >= 6 and (solo.isupper() or solo.istitle()):
            return True
        return False
    alpha_chars = sum(1 for c in text if c.isalpha())
    if alpha_chars == 0:
        return False
    upper_ratio = sum(1 for c in text if c.isupper()) / alpha_chars
    if text.endswith((".", "?", ",")):
        return False
    if upper_ratio > 0.65 and len(words) <= 10:
        return True
    if text.istitle() and len(words) <= 12:
        return True
    if text.lower().startswith(("chapter", "section", "appendix")):
        return True
    if HEADING_RE.match(text):
        return True
    return False


def _find_line_index(lines: Sequence[str], title: str) -> Optional[int]:
    normalized_title = title.lower()
    for idx, line in enumerate(lines):
        if normalized_title in line.lower():
            return idx
    return None


def collect_sections(pages: Sequence[PageContent]) -> List[SectionBoundary]:
    """Collect headings across pages, sorted by document order."""
    sections: List[SectionBoundary] = []
    for page in pages:
        sections.extend(detect_headings(page))
    sections.sort(key=lambda s: (s.page, s.line_index))
    return sections


def find_section(sections: Sequence[SectionBoundary], title: str) -> Optional[SectionBoundary]:
    """Locate a section boundary by case-insensitive title match."""
    title_lower = title.lower()
    for section in sections:
        if section.kind != "section":
            continue
        if section.title.lower() == title_lower:
            return section
    return None


def iter_section_text(
    pages: Sequence[PageContent],
    sections: Sequence[SectionBoundary],
    start_title: str,
    end_titles: Iterable[str],
) -> List[Tuple[int, str]]:
    """Return lines within the section bounded by start_title and the next matching end title."""
    start = find_section(sections, start_title)
    if not start:
        return []

    end_candidates = {title.lower() for title in end_titles}
    subsequent_sections = [
        section
        for section in sections
        if (section.page, section.line_index) > (start.page, start.line_index)
        and section.kind == "section"
        and section.title.lower() in end_candidates
    ]
    end = subsequent_sections[0] if subsequent_sections else None

    collected: List[Tuple[int, str]] = []
    for page in pages:
        if page.number < start.page:
            continue
        if end and page.number > end.page:
            break
        for idx, line in enumerate(page.lines):
            if (page.number, idx) <= (start.page, start.line_index):
                continue
            if end and (page.number, idx) >= (end.page, end.line_index):
                break
            collected.append((page.number, line))
    return collected


@dataclass(slots=True)
class _CalloutAccumulator:
    """Tracks callout metadata while collecting section text."""

    title: str
    start_page: int
    lines: List[str] = field(default_factory=list)
    pages: set[int] = field(default_factory=set)

    def add_line(self, line: str, page: int) -> None:
        cleaned = _clean_line(line)
        if cleaned is None:
            return
        self.lines.append(cleaned)
        self.pages.add(page)

    def to_metadata(
        self,
        doc: BaseDocument,
        section_index: int,
        callout_index: int,
    ) -> Tuple[Dict[str, Any], EvidenceSpan]:
        text = _compose_section_text([self.title] + self.lines) if self.lines else self.title
        anchor_page = min(self.pages) if self.pages else self.start_page
        evidence = EvidenceSpan(
            id=doc.stable_id(
                "callout_span",
                self.title,
                anchor_page,
                section_index,
                callout_index,
            ),
            text=text[:512],
            page=anchor_page,
        )
        metadata = {
            "id": doc.stable_id(
                "callout",
                self.title,
                anchor_page,
                section_index,
                callout_index,
            ),
            "title": self.title,
            "text": text,
            "pages": sorted(self.pages) if self.pages else [anchor_page],
            "evidence_span_id": evidence.id,
        }
        return metadata, evidence


@dataclass(slots=True)
class _SectionAccumulator:
    """Accumulates lines belonging to a single logical section."""

    title: Optional[str]
    level: Optional[int]
    first_page: Optional[int]
    lines: List[str] = field(default_factory=list)
    callouts: List[_CalloutAccumulator] = field(default_factory=list)
    page_hits: List[int] = field(default_factory=list)

    def add_line(self, line: str, page: int) -> None:
        cleaned = _clean_line(line)
        if cleaned is None:
            return
        self.lines.append(cleaned)
        self.page_hits.append(page)

    def add_blank(self) -> None:
        if not self.lines or self.lines[-1] != "":
            self.lines.append("")

    def has_content(self) -> bool:
        return any(line.strip() for line in self.lines)

    def start_callout(self, title: str, page: int) -> _CalloutAccumulator:
        callout = _CalloutAccumulator(title=title, start_page=page)
        callout.pages.add(page)
        self.callouts.append(callout)
        heading = title if title.endswith(":") else f"{title}:"
        self.lines.append(heading)
        self.page_hits.append(page)
        return callout

    def finalize(self, doc: BaseDocument, index: int) -> Optional[SectionModel]:
        text = _compose_section_text(self.lines)
        if not text.strip():
            return None

        page_anchor = self.first_page or (self.page_hits[0] if self.page_hits else 1)
        evidence_span = EvidenceSpan(
            id=doc.stable_id("section_span", self.title or "body", page_anchor, index),
            text=text[:1024],
            page=page_anchor,
        )
        evidence_spans = [evidence_span]
        metadata: Dict[str, Any] = {}

        if self.callouts:
            callout_meta: List[Dict[str, Any]] = []
            for callout_index, callout in enumerate(self.callouts, start=1):
                meta, callout_evidence = callout.to_metadata(doc, index, callout_index)
                callout_meta.append(meta)
                evidence_spans.append(callout_evidence)
            metadata["callouts"] = callout_meta

        section = SectionModel(
            id=doc.stable_id(
                "section", self.title or f"section_{index:03d}", page_anchor, index
            ),
            title=self.title,
            level=self.level,
            text=text,
            page_anchor=page_anchor,
            evidence_spans=evidence_spans,
            metadata=metadata,
        )
        return section


def build_sections(doc: BaseDocument, pages: Sequence[PageContent]) -> List[SectionModel]:
    """Return section objects with callout handling and provenance."""

    boundaries = collect_sections(pages)
    boundary_map: Dict[Tuple[int, int], SectionBoundary] = {
        (boundary.page, boundary.line_index): boundary for boundary in boundaries
    }

    results: List[SectionModel] = []
    current_section: Optional[_SectionAccumulator] = None
    current_callout: Optional[_CalloutAccumulator] = None
    callout_pending_blank = False

    for page in pages:
        for idx, raw_line in enumerate(page.lines):
            boundary = boundary_map.get((page.number, idx))
            if boundary:
                if boundary.kind == "section":
                    if current_section and current_section.has_content():
                        flushed = current_section.finalize(doc, len(results) + 1)
                        if flushed:
                            results.append(flushed)
                    current_section = _SectionAccumulator(
                        title=boundary.title,
                        level=boundary.level,
                        first_page=page.number,
                    )
                    current_callout = None
                    callout_pending_blank = False
                    continue

                if current_section is None:
                    current_section = _SectionAccumulator(
                        title=None, level=None, first_page=page.number
                    )
                current_callout = current_section.start_callout(boundary.title, page.number)
                callout_pending_blank = False
                continue

            normalized = normalize_text_artifacts(raw_line)
            text = normalized.strip()
            if not text:
                if current_section:
                    current_section.add_blank()
                if current_callout:
                    callout_pending_blank = True
                continue

            if current_section is None:
                current_section = _SectionAccumulator(
                    title=None, level=None, first_page=page.number
                )

            if current_callout:
                if callout_pending_blank and not _looks_like_callout_continuation(text):
                    current_callout = None
                    callout_pending_blank = False
                if current_callout:
                    current_callout.add_line(text, page.number)
            current_section.add_line(text, page.number)
            callout_pending_blank = False

        callout_pending_blank = False

    if current_section and current_section.has_content():
        flushed = current_section.finalize(doc, len(results) + 1)
        if flushed:
            results.append(flushed)

    return results


def _clean_line(text: str) -> Optional[str]:
    if text is None:
        return None
    cleaned = normalize_text_artifacts(text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = cleaned.strip()
    return cleaned or None


def _compose_section_text(lines: List[str]) -> str:
    paragraphs: List[str] = []
    buffer: List[str] = []

    def flush_buffer() -> None:
        if buffer:
            joined = " ".join(buffer)
            joined = re.sub(r"\s+", " ", joined).strip()
            if joined:
                paragraphs.append(joined)
            buffer.clear()

    for line in lines:
        if not line:
            flush_buffer()
            continue
        if BULLET_RE.match(line.strip()):
            flush_buffer()
            paragraphs.append(line.strip())
            continue
        buffer.append(line.strip())

    flush_buffer()
    return "\n\n".join(paragraphs).strip()


def _looks_like_callout_continuation(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if BULLET_RE.match(stripped):
        return True
    if stripped.isupper():
        return True
    if len(stripped.split()) <= 10:
        return True
    return False
