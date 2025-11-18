"""Paragraph extraction and storage helpers."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from medparse.ingest.models import PageData

from .hash import normalize_paragraph_text, stable_par_hash
from .headers import is_boilerplate_line, strip_boilerplate

HEADER_RE = re.compile(r"^page\s+\d+", re.IGNORECASE)
FOOTER_RE = re.compile(r"^\d+\s*/\s*\d+$")
PURE_DIGITS_RE = re.compile(r"^\d{1,4}$")
DOT_LEADER_RE = re.compile(r"\.{4,}\s*\d+$")
LIST_BULLET_RE = re.compile(r"^(?:[\-\u2022\u2023\u25E6\*]\s+|\d+[\).]\s+)")
LIST_MARKER_RE = re.compile(r"^(?:[\-\u2022\u2023\u25E6\*]+|\d+[\).])\s+")
TOC_LINE_PATTERN = re.compile(r"(?:\.{2,}|…|\s{4,})\s*\d{1,4}\s*$")
TRAILING_PAGE_NUMBER = re.compile(r"\s\d{1,4}\s*$")
CHAPTER_LINE_PATTERN = re.compile(r"^\s*(?:chapter|section)\s+[A-Z0-9IVXLC]+", re.IGNORECASE)
ADDRESS_TOKEN_RE = re.compile(
    r"\b(fax|telephone|tel\.?|suite|drive|road|street|st\.|ave|avenue|corporate|parkway|p\.?\s*o\.|box|japan|u\.s\.a|usa|korea|australia|telephone:|fax:)\b",
    re.IGNORECASE,
)
ZIP_TOKEN_RE = re.compile(r"\b[A-Z]{2}\s*\d{3,5}(?:-\d{3,4})?\b")


@dataclass(slots=True)
class Paragraph:
    """Paragraph detected on a page with origin metadata."""

    id: str
    page: int
    text: str
    char_span: Tuple[int, int]
    line_span: Optional[Tuple[int, int]] = None
    column_id: Optional[int] = None
    paragraph_type: str = "body"
    lists: List[str] = field(default_factory=list)


def _strip_list_marker(value: str) -> str:
    cleaned = LIST_MARKER_RE.sub("", value or "", count=1).strip()
    return normalize_paragraph_text(cleaned)


def _looks_like_address(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    digits = sum(char.isdigit() for char in text)
    if digits >= 6 and ("," in text or "-" in text):
        if ADDRESS_TOKEN_RE.search(text) or ZIP_TOKEN_RE.search(text):
            return True
    if ADDRESS_TOKEN_RE.search(text) and digits >= 3:
        return True
    if "telephone" in lowered or "fax" in lowered:
        return True
    if ZIP_TOKEN_RE.search(text):
        return True
    return False


def _looks_like_heading_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.isupper() and len(stripped.split()) <= 8:
        return True
    if CHAPTER_LINE_PATTERN.match(stripped):
        return True
    return False


def _looks_like_toc(lines: List[str], normalized: str, page_number: int) -> bool:
    if page_number > 10:
        return False
    lowered = normalized.lower()
    if "table of contents" in lowered or lowered.startswith("contents"):
        return True
    line_hits = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if TOC_LINE_PATTERN.search(stripped):
            line_hits += 1
            continue
        if TRAILING_PAGE_NUMBER.search(stripped) and len(stripped.split()) >= 3:
            line_hits += 1
    if line_hits >= max(1, len(lines) - 1):
        return True
    has_chapter = any(CHAPTER_LINE_PATTERN.match(line.strip()) for line in lines if line.strip())
    dotted = normalized.count("..")
    if has_chapter and dotted:
        return True
    if dotted >= 4:
        return True
    return False


def _classify_paragraph(lines: List[str], normalized: str, page_number: int) -> str:
    if _looks_like_address(normalized):
        return "address"
    if _looks_like_heading_line(normalized):
        return "heading"
    if _looks_like_toc(lines, normalized, page_number):
        return "toc"
    return "body"


def iter_paragraphs(
    pages: Iterable[PageData],
    *,
    join_hyphens: bool = True,
    drop_headers: bool = True,
    drop_footers: bool = True,
    toc_pages: Optional[Iterable[int]] = None,
) -> Iterator[Paragraph]:
    """Yield normalized paragraphs from the provided pages."""

    toc_page_set = {int(page) for page in (toc_pages or []) if isinstance(page, int)}

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
        text_buffer: List[str] = []
        text_start_offset: Optional[int] = None
        text_end_offset: Optional[int] = None
        text_start_line_idx: Optional[int] = None
        text_last_line_idx: Optional[int] = None
        list_buffer: List[str] = []
        list_start_offset: Optional[int] = None
        list_end_offset: Optional[int] = None
        list_start_line_idx: Optional[int] = None
        list_last_line_idx: Optional[int] = None
        para_count = 0
        toc_override = page.number in toc_page_set

        def _emit_paragraph(
            raw_lines: List[str],
            text_value: str,
            start_offset: Optional[int],
            end_offset: Optional[int],
            start_idx: Optional[int],
            end_idx: Optional[int],
            *,
            paragraph_type: str = "body",
            list_payload: Optional[List[str]] = None,
        ) -> Optional[Paragraph]:
            nonlocal para_count
            normalized = normalize_paragraph_text(text_value)
            if not normalized:
                return None
            para_type = paragraph_type
            if toc_override:
                para_type = "toc"
            elif paragraph_type == "body":
                para_type = _classify_paragraph(raw_lines, normalized, page.number)
            para_id = f"page{page.number}_para{para_count}"
            para_count += 1
            span_start = int(start_offset or 0)
            span_end = int(end_offset or span_start + len(normalized))
            line_span = None
            if start_idx is not None and end_idx is not None:
                line_span = (start_idx, end_idx)
            return Paragraph(
                id=para_id,
                page=page.number,
                text=normalized,
                char_span=(span_start, span_end),
                line_span=line_span,
                paragraph_type=para_type,
                lists=list(list_payload or []),
            )

        def _flush_text_buffer() -> Optional[Paragraph]:
            nonlocal text_buffer, text_start_offset, text_end_offset, text_start_line_idx, text_last_line_idx
            if not text_buffer:
                return None
            text_value = _flush_buffer(text_buffer, join_hyphens=join_hyphens)
            paragraph = _emit_paragraph(
                list(text_buffer),
                text_value,
                text_start_offset,
                text_end_offset,
                text_start_line_idx,
                text_last_line_idx,
            )
            text_buffer = []
            text_start_offset = None
            text_end_offset = None
            text_start_line_idx = None
            text_last_line_idx = None
            return paragraph

        def _flush_list_buffer() -> Optional[Paragraph]:
            nonlocal list_buffer, list_start_offset, list_end_offset, list_start_line_idx, list_last_line_idx
            if not list_buffer:
                return None
            text_value = " ".join(list_buffer)
            paragraph = _emit_paragraph(
                list(list_buffer),
                text_value,
                list_start_offset,
                list_end_offset,
                list_start_line_idx,
                list_last_line_idx,
                paragraph_type="list",
                list_payload=list(list_buffer),
            )
            list_buffer = []
            list_start_offset = None
            list_end_offset = None
            list_start_line_idx = None
            list_last_line_idx = None
            return paragraph

        for line_idx, (raw_line, line_start, line_end) in enumerate(line_offsets):
            stripped = raw_line.strip()
            if not stripped:
                paragraph = _flush_text_buffer()
                if paragraph:
                    yield paragraph
                list_paragraph = _flush_list_buffer()
                if list_paragraph:
                    yield list_paragraph
                continue

            if is_boilerplate_line(stripped):
                continue

            is_bullet_line = bool(LIST_BULLET_RE.match(stripped))
            is_heading_candidate = stripped.isupper() and len(stripped.split()) <= 6

            if is_bullet_line:
                paragraph = _flush_text_buffer()
                if paragraph:
                    yield paragraph
                cleaned_item = _strip_list_marker(stripped)
                if cleaned_item:
                    if list_start_offset is None:
                        leading_ws = len(raw_line) - len(raw_line.lstrip())
                        list_start_offset = line_start + leading_ws
                    list_end_offset = line_end
                    if list_start_line_idx is None:
                        list_start_line_idx = line_idx
                    list_last_line_idx = line_idx
                    list_buffer.append(cleaned_item)
                continue

            list_paragraph = _flush_list_buffer()
            if list_paragraph:
                yield list_paragraph

            if text_buffer and is_heading_candidate:
                paragraph = _flush_text_buffer()
                if paragraph:
                    yield paragraph

            if text_buffer and text_buffer[-1].endswith("-") and join_hyphens:
                text_buffer[-1] = text_buffer[-1][:-1] + stripped
            else:
                text_buffer.append(stripped)

            if text_start_offset is None:
                leading_ws = len(raw_line) - len(raw_line.lstrip())
                text_start_offset = line_start + leading_ws
            text_end_offset = line_end
            if text_start_line_idx is None:
                text_start_line_idx = line_idx
            text_last_line_idx = line_idx

        paragraph = _flush_text_buffer()
        if paragraph:
            yield paragraph
        list_paragraph = _flush_list_buffer()
        if list_paragraph:
            yield list_paragraph


def build_paragraph_store(
    doc_id: str,
    pages: Sequence[PageData],
    *,
    join_hyphens: bool = True,
    drop_headers: bool = True,
    drop_footers: bool = True,
    detect_columns: bool = False,
    toc_pages: Optional[Iterable[int]] = None,
) -> tuple[Dict[str, Dict[str, object]], bool]:
    """Construct a hashed paragraph store for downstream evidence references."""

    store: Dict[str, Dict[str, object]] = {}
    dedup_applied = False
    global_index = 0
    line_columns_per_page: Dict[int, Dict[int, int]] = {}
    if detect_columns:
        line_columns_per_page = _build_line_column_map(pages)

    for paragraph in iter_paragraphs(
        pages,
        join_hyphens=join_hyphens,
        drop_headers=drop_headers,
        drop_footers=drop_footers,
        toc_pages=toc_pages,
    ):
        hash_id = stable_par_hash(doc_id, paragraph.page, paragraph.text)
        entry = store.get(hash_id)
        column_id = None
        if detect_columns:
            column_id = _column_id_for_paragraph(
                line_columns_per_page.get(paragraph.page, {}),
                paragraph.line_span,
            )
            paragraph.column_id = column_id
        occurrence = {
            "page": paragraph.page,
            "char_span": list(paragraph.char_span),
        }
        if column_id is not None:
            occurrence["column_id"] = column_id

        if entry is None:
            store[hash_id] = {
                "id": paragraph.id,
                "text": paragraph.text,
                "page": paragraph.page,
                "char_span": list(paragraph.char_span),
                "length": len(paragraph.text),
                "order": [global_index],
                "occurrences": [occurrence],
                "column_id": column_id,
                "type": paragraph.paragraph_type,
                "lists": list(paragraph.lists or []),
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
            if column_id is not None and entry.get("column_id") is None:
                entry["column_id"] = column_id
            existing_type = entry.get("type")
            if (not existing_type or existing_type == "body") and paragraph.paragraph_type != "body":
                entry["type"] = paragraph.paragraph_type
            if paragraph.lists and not entry.get("lists"):
                entry["lists"] = list(paragraph.lists)
        global_index += 1

    for entry in store.values():
        entry.setdefault("pages", [entry.get("page")])
        entry.setdefault("type", "body")
        entry.setdefault("lists", [])

    return store, dedup_applied


def reflow_two_column_pages(
    pages: Sequence[PageData],
    *,
    min_ratio: float = 2.2,
    min_blocks: int = 8,
) -> None:
    """Normalize two-column pages into column-major reading order."""

    for page in pages:
        _maybe_reflow_page_columns(page, min_ratio=min_ratio, min_blocks=min_blocks)


def _maybe_reflow_page_columns(
    page: PageData,
    *,
    min_ratio: float,
    min_blocks: int,
) -> None:
    if not page.blocks:
        return

    candidates = _detect_column_blocks(page, min_ratio=min_ratio, min_blocks=min_blocks)
    if not candidates:
        return

    new_lines: List[str] = []
    column_map: Dict[int, int] = {}

    for entry in candidates:
        text = entry["text"] or ""
        block_lines = text.splitlines()
        appended = False
        for raw_line in block_lines:
            normalized = raw_line.strip()
            if not normalized:
                new_lines.append("")
                continue
            new_lines.append(normalized)
            column_map[len(new_lines) - 1] = entry["column_id"]
            appended = True
        if appended and new_lines and new_lines[-1].strip():
            new_lines.append("")

    while new_lines and not new_lines[-1].strip():
        idx = len(new_lines) - 1
        new_lines.pop()
        column_map.pop(idx, None)

    if not new_lines:
        return

    page.lines = new_lines
    page.text = "\n".join(new_lines)
    setattr(page, "column_map", column_map)


def _detect_column_blocks(
    page: PageData,
    *,
    min_ratio: float,
    min_blocks: int,
) -> List[Dict[str, object]]:
    blocks = getattr(page, "blocks", []) or []
    candidates: List[Dict[str, object]] = []
    for block in blocks:
        text = getattr(block, "text", "")
        bbox = getattr(block, "bbox", None)
        if not bbox or not text or not text.strip():
            continue
        x0, y0, x1, y1 = bbox
        width = x1 - x0
        if width <= 0:
            continue
        candidates.append(
            {
                "text": text,
                "bbox": bbox,
                "x_center": (x0 + x1) / 2.0,
                "y_top": y0,
                "x_start": x0,
                "width": width,
            }
        )

    if len(candidates) < min_blocks:
        return []

    widths = [entry["width"] for entry in candidates if entry["width"] > 0]
    if not widths:
        return []

    try:
        median_width = median(widths)
    except Exception:
        return []
    if median_width <= 0:
        return []

    page_min = min(entry["bbox"][0] for entry in candidates)
    page_max = max(entry["bbox"][2] for entry in candidates)
    page_width = page_max - page_min
    if page_width <= 0:
        return []

    ratio = page_width / float(median_width)
    if ratio < min_ratio:
        return []

    centers = [entry["x_center"] for entry in candidates]
    clustered = _cluster_columns(centers)
    if not clustered:
        return []

    center_positions, assignments = clustered
    if len(assignments) != len(candidates):
        return []

    counts = Counter(assignments)
    if counts[0] == 0 or counts[1] == 0:
        return []

    if abs(center_positions[1] - center_positions[0]) < 40:
        return []

    for entry, column_id in zip(candidates, assignments):
        entry["column_id"] = column_id

    candidates.sort(key=lambda entry: (entry["column_id"], entry["y_top"], entry["x_start"]))
    return candidates


def _build_line_column_map(
    pages: Sequence[PageData],
    *,
    min_ratio: float = 2.2,
    min_lines: int = 8,
) -> Dict[int, Dict[int, int]]:
    column_map: Dict[int, Dict[int, int]] = {}
    for page in pages:
        explicit_map = getattr(page, "column_map", None)
        if isinstance(explicit_map, dict) and explicit_map:
            column_map[page.number] = dict(explicit_map)
            continue
        mapping = _detect_line_columns(page, min_ratio=min_ratio, min_lines=min_lines)
        if mapping:
            column_map[page.number] = mapping
    return column_map


def _column_id_for_paragraph(
    line_columns: Dict[int, int],
    line_span: Optional[Tuple[int, int]],
) -> Optional[int]:
    if not line_columns or not line_span:
        return None
    start, end = line_span
    counts: Dict[int, int] = defaultdict(int)
    for idx in range(max(0, start), end + 1):
        column = line_columns.get(idx)
        if column is not None:
            counts[column] += 1
    if not counts:
        return None
    column_id = max(counts.items(), key=lambda item: (item[1], -item[0]))[0]
    return column_id


def _detect_line_columns(
    page: PageData,
    *,
    min_ratio: float,
    min_lines: int,
) -> Dict[int, int]:
    if not page.blocks or len(page.lines) < min_lines:
        return {}
    line_bboxes = _map_line_bboxes(page)
    if len(line_bboxes) < min_lines:
        return {}
    widths = [bbox[2] - bbox[0] for bbox in line_bboxes.values() if bbox and bbox[2] > bbox[0]]
    if not widths:
        return {}
    try:
        median_width = median(widths)
    except Exception:
        return {}
    x0_values = [bbox[0] for bbox in line_bboxes.values()]
    x1_values = [bbox[2] for bbox in line_bboxes.values()]
    page_width = max(x1_values) - min(x0_values)
    if not median_width or page_width / median_width < min_ratio:
        return {}
    line_items = sorted(line_bboxes.items(), key=lambda item: item[0])
    centers = [(bbox[0] + bbox[2]) / 2 for _, bbox in line_items]
    cluster = _cluster_columns(centers)
    if cluster is None:
        return {}
    _, assignments = cluster
    column_map: Dict[int, int] = {}
    for (line_idx, _), column_id in zip(line_items, assignments):
        column_map[line_idx] = column_id
    return column_map


def _map_line_bboxes(page: PageData) -> Dict[int, Tuple[float, float, float, float]]:
    mapping: Dict[int, Tuple[float, float, float, float]] = {}
    if not page.blocks:
        return mapping
    line_cursor = 0
    total_lines = len(page.lines)
    normalized_lines = [re.sub(r"\s+", " ", line).strip() for line in page.lines]
    for block in page.blocks:
        bbox = block.bbox
        if not bbox or not block.text:
            continue
        block_lines = [re.sub(r"\s+", " ", line).strip() for line in block.text.splitlines() if line.strip()]
        for block_line in block_lines:
            if not block_line:
                continue
            while line_cursor < total_lines and not normalized_lines[line_cursor]:
                line_cursor += 1
            while line_cursor < total_lines and not _line_matches(normalized_lines[line_cursor], block_line):
                line_cursor += 1
            if line_cursor >= total_lines:
                break
            mapping[line_cursor] = bbox
            line_cursor += 1
    return mapping


def _line_matches(candidate: str, block_line: str) -> bool:
    if not candidate or not block_line:
        return False
    candidate_norm = candidate.lower()
    block_norm = block_line.lower()
    return candidate_norm.startswith(block_norm) or block_norm.startswith(candidate_norm)


def _cluster_columns(values: List[float]) -> Optional[Tuple[List[float], List[int]]]:
    if len(values) < 4:
        return None
    min_val = min(values)
    max_val = max(values)
    if abs(max_val - min_val) < 1.0:
        return None
    centers = [min_val, max_val]
    assignments = [0] * len(values)
    for _ in range(5):
        clusters = {0: [], 1: []}
        for idx, value in enumerate(values):
            target = 0 if abs(value - centers[0]) <= abs(value - centers[1]) else 1
            assignments[idx] = target
            clusters[target].append(value)
        for target in (0, 1):
            if clusters[target]:
                centers[target] = sum(clusters[target]) / len(clusters[target])
    if centers[0] > centers[1]:
        centers.reverse()
        assignments = [1 - val for val in assignments]
    if assignments.count(0) == 0 or assignments.count(1) == 0:
        return None
    return centers, assignments


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


__all__ = ["Paragraph", "iter_paragraphs", "build_paragraph_store", "compute_space_metrics", "reflow_two_column_pages"]
