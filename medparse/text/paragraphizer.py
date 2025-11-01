"""Paragraph extraction and storage helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple

from medparse.ingest.models import PageData

from .hash import normalize_paragraph_text, stable_par_hash
from .headers import is_boilerplate_line, strip_boilerplate

HEADER_RE = re.compile(r"^page\s+\d+", re.IGNORECASE)
FOOTER_RE = re.compile(r"^\d+\s*/\s*\d+$")
PURE_DIGITS_RE = re.compile(r"^\d{1,4}$")
DOT_LEADER_RE = re.compile(r"\.{4,}\s*\d+$")


@dataclass(slots=True)
class Paragraph:
    """Paragraph detected on a page with origin metadata."""

    id: str
    page: int
    text: str
    char_span: Tuple[int, int]


def iter_paragraphs(
    pages: Iterable[PageData],
    *,
    join_hyphens: bool = True,
    drop_headers: bool = True,
    drop_footers: bool = True,
) -> Iterator[Paragraph]:
    """Yield normalized paragraphs from the provided pages."""

    for page in pages:
        lines = list(page.lines or [])
        if not lines and page.text:
            lines = page.text.splitlines()
        if not lines:
            continue

        lines = strip_boilerplate(lines)

        if drop_headers:
            lines = _drop_header(lines)
        if drop_footers:
            lines = _drop_footer(lines)

        if not lines:
            continue

        line_offsets = _line_offsets(lines)
        buffer: List[str] = []
        start_offset: int | None = None
        end_offset: int | None = None
        para_count = 0

        for (raw_line, line_start, line_end) in line_offsets:
            stripped = raw_line.strip()
            if not stripped:
                if buffer:
                    text = _flush_buffer(buffer, join_hyphens=join_hyphens)
                    normalized = normalize_paragraph_text(text)
                    if normalized:
                        para_id = f"page{page.number}_para{para_count}"
                        para_count += 1
                        yield Paragraph(
                            id=para_id,
                            page=page.number,
                            text=normalized,
                            char_span=(start_offset or line_start, end_offset or line_end),
                        )
                buffer = []
                start_offset = None
                end_offset = None
                continue

            if is_boilerplate_line(stripped):
                continue

            if buffer and re.match(r"^\d+[\).]", stripped):
                text = _flush_buffer(buffer, join_hyphens=join_hyphens)
                normalized = normalize_paragraph_text(text)
                if normalized:
                    para_id = f"page{page.number}_para{para_count}"
                    para_count += 1
                    yield Paragraph(
                        id=para_id,
                        page=page.number,
                        text=normalized,
                        char_span=(start_offset or line_start, end_offset or line_end),
                    )
                buffer = []
                start_offset = None
                end_offset = None

            if buffer and stripped.isupper() and len(stripped.split()) <= 6:
                text = _flush_buffer(buffer, join_hyphens=join_hyphens)
                normalized = normalize_paragraph_text(text)
                if normalized:
                    para_id = f"page{page.number}_para{para_count}"
                    para_count += 1
                    yield Paragraph(
                        id=para_id,
                        page=page.number,
                        text=normalized,
                        char_span=(start_offset or line_start, end_offset or line_end),
                    )
                buffer = []
                start_offset = None
                end_offset = None

            if buffer and buffer[-1].endswith("-") and join_hyphens:
                buffer[-1] = buffer[-1][:-1] + stripped
            else:
                buffer.append(stripped)

            if start_offset is None:
                leading_ws = len(raw_line) - len(raw_line.lstrip())
                start_offset = line_start + leading_ws
            end_offset = line_end

        if buffer:
            text = _flush_buffer(buffer, join_hyphens=join_hyphens)
            normalized = normalize_paragraph_text(text)
            if normalized:
                para_id = f"page{page.number}_para{para_count}"
                yield Paragraph(
                    id=para_id,
                    page=page.number,
                    text=normalized,
                    char_span=(start_offset or 0, end_offset or len(normalized)),
                )


def build_paragraph_store(
    doc_id: str,
    pages: Sequence[PageData],
    *,
    join_hyphens: bool = True,
    drop_headers: bool = True,
    drop_footers: bool = True,
) -> tuple[Dict[str, Dict[str, object]], bool]:
    """Construct a hashed paragraph store for downstream evidence references."""

    store: Dict[str, Dict[str, object]] = {}
    dedup_applied = False
    global_index = 0

    for paragraph in iter_paragraphs(
        pages,
        join_hyphens=join_hyphens,
        drop_headers=drop_headers,
        drop_footers=drop_footers,
    ):
        hash_id = stable_par_hash(doc_id, paragraph.page, paragraph.text)
        entry = store.get(hash_id)
        occurrence = {
            "page": paragraph.page,
            "char_span": list(paragraph.char_span),
        }

        if entry is None:
            store[hash_id] = {
                "id": paragraph.id,
                "text": paragraph.text,
                "page": paragraph.page,
                "char_span": list(paragraph.char_span),
                "length": len(paragraph.text),
                "order": [global_index],
                "occurrences": [occurrence],
            }
        else:
            dedup_applied = True
            occurrences = entry.setdefault("occurrences", [])
            occurrences.append(occurrence)
            order = entry.setdefault("order", [])
            order.append(global_index)
            pages_mapping = entry.setdefault("pages", [])
            if paragraph.page not in pages_mapping:
                pages_mapping.append(paragraph.page)
        global_index += 1

    for entry in store.values():
        entry.setdefault("pages", [entry.get("page")])

    return store, dedup_applied


def _drop_header(lines: List[str]) -> List[str]:
    if not lines:
        return lines
    first = lines[0].strip()
    if (
        not first
        or HEADER_RE.match(first)
        or PURE_DIGITS_RE.match(first)
        or DOT_LEADER_RE.search(first)
        or is_boilerplate_line(first)
    ):
        return lines[1:]
    return lines


def _drop_footer(lines: List[str]) -> List[str]:
    if not lines:
        return lines
    last = lines[-1].strip()
    if (
        not last
        or FOOTER_RE.match(last)
        or HEADER_RE.match(last)
        or DOT_LEADER_RE.search(last)
        or is_boilerplate_line(last)
    ):
        return lines[:-1]
    return lines


def _line_offsets(lines: Sequence[str]) -> List[Tuple[str, int, int]]:
    offsets: List[Tuple[str, int, int]] = []
    cursor = 0
    for line in lines:
        length = len(line)
        offsets.append((line, cursor, cursor + length))
        cursor += length + 1  # Account for newline separation
    return offsets


def _flush_buffer(buffer: List[str], *, join_hyphens: bool) -> str:
    if not buffer:
        return ""
    pieces: List[str] = []
    for line in buffer:
        if join_hyphens and pieces and pieces[-1].endswith("-"):
            pieces[-1] = pieces[-1][:-1] + line
        else:
            pieces.append(line)
    return " ".join(pieces)


def compute_space_metrics(pages: Sequence[PageData]) -> Dict[str, float]:
    """Estimate spacing quality across pages."""
    total_chars = 0
    space_chars = 0
    token_lengths: List[int] = []

    for page in pages:
        text = page.text or ""
        total_chars += len(text)
        space_chars += text.count(" ")
        tokens = re.findall(r"[A-Za-z0-9]{2,}", text)
        token_lengths.extend(len(token) for token in tokens)

    avg_token_length = float(sum(token_lengths) / len(token_lengths)) if token_lengths else 0.0
    space_ratio = float(space_chars / total_chars) if total_chars else 0.0
    return {
        "space_ratio": space_ratio,
        "avg_token_length": avg_token_length,
    }


__all__ = ["Paragraph", "iter_paragraphs", "build_paragraph_store", "compute_space_metrics"]
