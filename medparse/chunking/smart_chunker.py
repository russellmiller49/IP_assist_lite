"""Layout-aware chunking utilities for RAG-friendly payloads."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from hashlib import blake2b
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from medparse.ingest.models import Heading, PageData
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_BULLET_RE = re.compile(r"^\s*([\-\u2022\u2023\u25E6\*\u2219]\s+|[A-Z]\)|[A-Z]\.)")
_ORDERED_RE = re.compile(r"^\s*(?:\d+|[ivxlcdmIVXLCDM]+)[\.\)]\s+")
_SAFETY_KEYWORDS = {
    "danger",
    "warning",
    "caution",
    "notice",
    "note",
    "attention",
}


@dataclass(slots=True)
class Chunk:
    """Chunk metadata emitted to downstream retrieval systems."""

    id: str
    hash: str
    type: str  # "text" | "table" | "safety" | "recommendation"
    heading_path: List[str] = field(default_factory=list)
    page_range: List[int] = field(default_factory=list)
    span_hashes: List[str] = field(default_factory=list)
    token_len: int = 0
    anchors: List[str] = field(default_factory=list)
    safety_level: Optional[str] = None
    column_id: Optional[int] = None


class SmartChunker:
    """Chunk paragraphs into overlapping windows while respecting layout boundaries."""

    def __init__(
        self,
        token_min: int = 200,
        token_max: int = 500,
        overlap_ratio: float = 0.15,
        enable_c99: bool = False,
    ) -> None:
        self.token_min = max(1, int(token_min))
        self.token_max = max(self.token_min, int(token_max))
        self.overlap_ratio = max(0.0, min(float(overlap_ratio or 0.0), 0.4))
        self.enable_c99 = enable_c99

    def from_blocks(
        self,
        blocks: Iterable[Dict[str, Any]],
        headings_index: Dict[int, List[Dict[str, Any]]],
        safety_headers: Dict[int, List[Dict[str, Any]]],
        tables: Dict[int, List[Dict[str, Any]]],
    ) -> List[Chunk]:
        """Return chunk records for the provided block stream."""

        normalized = list(_normalize_blocks(blocks, headings_index))
        if not normalized:
            return []

        chunks: List[Chunk] = []
        buffer = _ChunkBuffer(self)

        for block in normalized:
            block_type = block.get("block_type") or "text"
            block_tokens = int(block.get("token_len") or 0)
            if buffer and buffer.chunk_type and buffer.chunk_type != block_type:
                if buffer:
                    chunks.append(buffer.finalize(len(chunks)))
                buffer = _ChunkBuffer(self)

            if (
                block_type not in {"table", "safety"}
                and buffer
                and buffer.token_len
                and buffer.token_len + block_tokens > self.token_max
            ):
                chunks.append(buffer.finalize(len(chunks)))
                buffer = _ChunkBuffer(self)

            if buffer.should_break(block):
                chunks.append(buffer.finalize(len(chunks)))
                buffer = _ChunkBuffer(self)

            buffer.add(block)

            if block_type in {"table", "safety"}:
                continue

            if buffer.token_len >= self.token_max:
                exceeds_list = buffer.list_mode is not None
                chunks.append(buffer.finalize(len(chunks)))
                buffer = _ChunkBuffer(self) if exceeds_list else buffer.bootstrap_with_overlap()

        if buffer:
            chunks.append(buffer.finalize(len(chunks)))

        return chunks


class _ChunkBuffer:
    """Internal builder that accumulates paragraph blocks."""

    def __init__(self, chunker: SmartChunker) -> None:
        self.chunker = chunker
        self.blocks: List[Dict[str, Any]] = []
        self.token_len = 0
        self.chunk_type: Optional[str] = None
        self.heading_path: List[str] = []
        self.anchors: List[str] = []
        self.safety_level: Optional[str] = None
        self.column_id: Optional[int] = None
        self.list_mode: Optional[str] = None

    def __bool__(self) -> bool:
        return bool(self.blocks)

    def add(self, block: Dict[str, Any]) -> None:
        if not block.get("span_hash"):
            return
        self.blocks.append(block)
        self.token_len += int(block.get("token_len") or 0)
        self.chunk_type = self.chunk_type or block.get("block_type") or "text"
        self.column_id = block.get("column_id", self.column_id)
        self.list_mode = block.get("list_type") or self.list_mode
        if not self.heading_path and block.get("heading_path"):
            self.heading_path = list(block.get("heading_path", []))
        if block.get("anchors"):
            combined = set(self.anchors)
            combined.update(block.get("anchors", []))
            self.anchors = sorted(combined)
        if not self.safety_level and block.get("safety_level"):
            self.safety_level = block.get("safety_level")

    def should_break(self, block: Dict[str, Any]) -> bool:
        if not self.blocks:
            return False
        if block.get("block_type") in {"table", "safety"}:
            return self.chunk_type not in {"table", "safety"}
        if block.get("column_id") is not None and self.column_id is not None and block.get("column_id") != self.column_id:
            return True
        if block.get("anchors") and set(block.get("anchors", [])) != set(self.anchors):
            return True
        current_heading = self.blocks[-1].get("heading_path") or []
        next_heading = block.get("heading_path") or []
        if current_heading and next_heading:
            shared = _shared_prefix_len(current_heading, next_heading)
            if shared < min(len(current_heading), len(next_heading)):
                return True
        if self.list_mode and block.get("list_type") != self.list_mode:
            # wrap up the bullet list before moving on
            return True
        if block.get("list_type") and self.list_mode != block.get("list_type"):
            return True
        if self.token_len < self.chunker.token_min:
            return False
        if block.get("force_break"):
            return True
        return False

    def finalize(self, index: int) -> Chunk:
        span_hashes = [block["span_hash"] for block in self.blocks if block.get("span_hash")]
        chunk_hash = _chunk_hash(span_hashes)
        pages = sorted({int(block.get("page") or 0) for block in self.blocks if block.get("page")})
        heading_path = _select_heading_path(self.blocks) or self.heading_path
        chunk = Chunk(
            id=f"chunk_{index + 1:04d}",
            hash=chunk_hash,
            type=self.chunk_type or "text",
            heading_path=heading_path,
            page_range=pages or [],
            span_hashes=span_hashes,
            token_len=self.token_len,
            anchors=list(self.anchors or []),
            safety_level=self.safety_level,
            column_id=self.column_id,
        )
        return chunk

    def bootstrap_with_overlap(self) -> "_ChunkBuffer":
        if not self.blocks:
            return _ChunkBuffer(self.chunker)
        overlap_size = max(1, int(len(self.blocks) * self.chunker.overlap_ratio))
        overlap_blocks = self.blocks[-overlap_size:]
        new_buffer = _ChunkBuffer(self.chunker)
        for block in overlap_blocks:
            new_buffer.add(block)
        return new_buffer


def _normalize_blocks(
    blocks: Iterable[Dict[str, Any]],
    headings_index: Dict[int, List[Dict[str, Any]]],
) -> Iterator[Dict[str, Any]]:
    for block in blocks:
        text = block.get("text") or ""
        token_len = block.get("token_len")
        if token_len is None:
            token_len = _estimate_tokens(text)
        payload = dict(block)
        payload["text"] = text
        payload["token_len"] = token_len
        payload["heading_path"] = block.get("heading_path") or _fallback_heading_path(block, headings_index)
        payload["span_hash"] = block.get("span_hash")
        payload["block_type"] = block.get("block_type") or "text"
        payload["anchors"] = list(block.get("anchors") or [])
        payload["page"] = block.get("page")
        payload["list_type"] = block.get("list_type")
        yield payload


def build_document_chunks(
    document: Any,
    pages: Sequence[PageData],
    *,
    settings: Dict[str, Any],
    mode: str = "smart",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return serialized chunks plus summary metrics for a document."""

    paragraph_store = getattr(document, "paragraph_store", None)
    if not isinstance(paragraph_store, dict) or not paragraph_store:
        return [], {"enabled": False, "reason": "paragraph_store_missing", "mode": mode}

    anchor_spans = {}
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if isinstance(pipeline_info, dict):
        spans = pipeline_info.get("anchor_spans")
        if isinstance(spans, dict):
            anchor_spans = {k: dict(v) for k, v in spans.items() if isinstance(v, dict)}

    tables_index = _collect_tables(document)
    safety_headers = _collect_safety_headers(document)
    blocks, heading_index = _build_blocks(
        paragraph_store,
        pages,
        anchor_spans=anchor_spans,
        safety_headers=safety_headers,
        tables=tables_index,
        max_tokens=int(settings.get("token_max", 500) or 500),
    )

    if not blocks:
        return [], {"enabled": False, "reason": "no_blocks", "mode": mode}

    chunker = SmartChunker(
        token_min=int(settings.get("token_min", 200) or 200),
        token_max=int(settings.get("token_max", 500) or 500),
        overlap_ratio=float(settings.get("overlap_ratio", 0.15) or 0.15),
        enable_c99=bool(settings.get("enable_c99", False)),
    )
    chunk_models = chunker.from_blocks(blocks, heading_index, safety_headers, tables_index)
    if not chunk_models:
        return [], {"enabled": False, "mode": mode, "reason": "no_chunks"}
    serialized = [
        {
            "id": chunk.id,
            "hash": chunk.hash,
            "type": chunk.type,
            "heading_path": chunk.heading_path,
            "page_range": chunk.page_range,
            "spans": chunk.span_hashes,
            "token_len": chunk.token_len,
            "anchors": chunk.anchors,
            "safety_level": chunk.safety_level,
        }
        for chunk in chunk_models
    ]
    avg_tokens = float(sum(chunk.token_len for chunk in chunk_models) / len(chunk_models)) if chunk_models else 0.0
    metrics = {
        "enabled": True,
        "mode": mode,
        "chunks_created": len(serialized),
        "avg_tokens": round(avg_tokens, 2),
        "token_min": chunker.token_min,
        "token_max": chunker.token_max,
        "overlap_ratio": chunker.overlap_ratio,
    }
    return serialized, metrics


def _collect_tables(document: Any) -> Dict[int, List[Dict[str, Any]]]:
    payload: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    tables = getattr(document, "tables", None)
    if not isinstance(tables, list):
        return payload
    for table in tables:
        if isinstance(table, dict):
            page = table.get("page")
            table_id = table.get("id")
        else:
            page = getattr(table, "page", None)
            table_id = getattr(table, "id", None)
        if page is None:
            continue
        payload[int(page)].append(
            {
                "id": table_id,
                "page": int(page),
                "table_type": (table.get("table_type") if isinstance(table, dict) else getattr(table, "table_type", None)),
            }
        )
    return payload


def _collect_safety_headers(document: Any) -> Dict[int, List[Dict[str, Any]]]:
    payload: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    blocks = getattr(document, "safety_blocks", None)
    if not isinstance(blocks, list):
        return payload
    for block in blocks:
        level = getattr(block, "level", None) if not isinstance(block, dict) else block.get("level")
        page = getattr(block, "page", None) if not isinstance(block, dict) else block.get("page")
        title = getattr(block, "title", None) if not isinstance(block, dict) else block.get("title")
        if page is None:
            continue
        payload[int(page)].append(
            {
                "title": title,
                "level": level,
            }
        )
    return payload


def _build_blocks(
    paragraph_store: Dict[str, Dict[str, Any]],
    pages: Sequence[PageData],
    *,
    anchor_spans: Dict[str, Dict[str, Any]],
    safety_headers: Dict[int, List[Dict[str, Any]]],
    tables: Dict[int, List[Dict[str, Any]]],
    max_tokens: int,
) -> Tuple[List[Dict[str, Any]], Dict[int, List[Dict[str, Any]]]]:
    heading_map = _build_heading_index(pages)
    page_offsets = _page_line_offsets(pages)
    occurrences = _iter_occurrences(paragraph_store)

    heading_stack: List[Dict[str, Any]] = []
    heading_cursors: Dict[int, int] = defaultdict(int)
    active_callout: Optional[Dict[str, Any]] = None
    blocks: List[Dict[str, Any]] = []
    current_page = None

    for occurrence in occurrences:
        page = int(occurrence.get("page") or 0)
        if current_page != page:
            current_page = page
            active_callout = None
        char_span = occurrence.get("char_span")
        line_index = _line_index_for_span(page_offsets.get(page, []), char_span)
        headings = heading_map.get(page, [])
        cursor = heading_cursors.get(page, 0)
        threshold = line_index if line_index is not None else math.inf
        while cursor < len(headings):
            candidate = headings[cursor]
            idx = candidate.get("line_index")
            if idx is not None and idx > threshold:
                break
            cursor += 1
            level = candidate.get("level") or 4
            kind = (candidate.get("kind") or "section").lower()
            title = candidate.get("title")
            if kind == "callout":
                active_callout = {
                    "title": title,
                    "level": _normalize_safety_level(title),
                }
                continue
            active_callout = None
            heading_stack = [item for item in heading_stack if (item.get("level") or 4) < level]
            heading_stack.append({"title": title, "level": level})
        heading_cursors[page] = cursor

        heading_path = [item["title"] for item in heading_stack if item.get("title")]
        list_type = _detect_list_type(occurrence.get("text") or "")
        anchors = _anchors_for_page(page, anchor_spans)
        block_type = "text"
        safety_level = None
        if active_callout:
            block_type = "safety"
            safety_level = active_callout.get("level")

        block = {
            "text": occurrence.get("text") or "",
            "page": page,
            "span_hash": occurrence.get("span_hash"),
            "token_len": _estimate_tokens(occurrence.get("text") or ""),
            "heading_path": heading_path,
            "heading_level": heading_stack[-1]["level"] if heading_stack else None,
            "list_type": list_type,
            "anchors": anchors,
            "block_type": block_type,
            "safety_level": safety_level,
            "column_id": occurrence.get("column_id"),
        }
        if max_tokens and block["token_len"] > max_tokens:
            blocks.extend(_split_block(block, max_tokens))
        else:
            blocks.append(block)

    return blocks, heading_map


def _iter_occurrences(store: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    occurrences: List[Tuple[int, Dict[str, Any]]] = []
    for span_hash, entry in store.items():
        orders = entry.get("order") or []
        occs = entry.get("occurrences") or []
        if not occs:
            occs = [
                {
                    "page": entry.get("page"),
                    "char_span": entry.get("char_span"),
                }
            ]
        if not orders:
            orders = list(range(len(occs)))
        for idx, occurrence in enumerate(occs):
            order = orders[idx] if idx < len(orders) else orders[-1]
            payload = {
                "order": order,
                "page": occurrence.get("page"),
                "char_span": occurrence.get("char_span"),
                "span_hash": span_hash,
                "text": entry.get("text"),
            }
            occurrences.append((order, payload))
    occurrences.sort(key=lambda item: item[0])
    return [payload for _, payload in occurrences]


def _build_heading_index(pages: Sequence[PageData]) -> Dict[int, List[Dict[str, Any]]]:
    payload: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for page in pages:
        headings = getattr(page, "headings", []) or []
        serialised = []
        for heading in headings:
            if isinstance(heading, Heading):
                serialised.append(
                    {
                        "title": heading.title,
                        "line_index": heading.line_index,
                        "level": heading.level or 4,
                        "kind": heading.kind,
                    }
                )
            else:
                serialised.append(
                    {
                        "title": heading.get("title"),
                        "line_index": heading.get("line_index"),
                        "level": heading.get("level", 4),
                        "kind": heading.get("kind"),
                    }
                )
        serialised.sort(key=lambda h: (h.get("line_index") or 0))
        payload[int(page.number)] = serialised
    return payload


def _page_line_offsets(pages: Sequence[PageData]) -> Dict[int, List[Tuple[int, int, int]]]:
    offsets: Dict[int, List[Tuple[int, int, int]]] = {}
    for page in pages:
        lines = page.lines or []
        cursor = 0
        page_offsets: List[Tuple[int, int, int]] = []
        for idx, line in enumerate(lines):
            start = cursor
            end = cursor + len(line)
            page_offsets.append((idx, start, end))
            cursor = end + 1
        offsets[int(page.number)] = page_offsets
    return offsets


def _line_index_for_span(
    offsets: List[Tuple[int, int, int]],
    char_span: Optional[Sequence[int]],
) -> Optional[int]:
    if not offsets or not char_span:
        return None
    try:
        start = min(int(char_span[0]), int(char_span[-1]))
    except (TypeError, ValueError):
        return None
    for idx, begin, end in offsets:
        if begin <= start <= end:
            return idx
    return offsets[-1][0] if offsets else None


def _anchors_for_page(page: int, anchors: Dict[str, Dict[str, Any]]) -> List[str]:
    scoped: List[str] = []
    for name, span in anchors.items():
        start = span.get("start_page")
        end = span.get("end_page", start)
        if start is None:
            continue
        try:
            start_page = int(start)
            end_page = int(end) if end is not None else start_page
        except (TypeError, ValueError):
            continue
        if start_page <= page <= end_page:
            scoped.append(name)
    return sorted(set(scoped))


def _split_block(block: Dict[str, Any], max_tokens: int) -> List[Dict[str, Any]]:
    """Split an oversized block into virtual segments capped by ``max_tokens``."""

    segments: List[Dict[str, Any]] = []
    remaining = int(block.get("token_len") or 0)
    idx = 0
    while remaining > 0:
        segment_tokens = min(max_tokens, remaining)
        segment = dict(block)
        segment["token_len"] = segment_tokens
        segment["segment_index"] = idx
        segments.append(segment)
        remaining -= segment_tokens
        idx += 1
    return segments


def _normalize_safety_level(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    lowered = title.lower()
    for keyword in _SAFETY_KEYWORDS:
        if keyword in lowered:
            return keyword
    return None


def _detect_list_type(text: str) -> Optional[str]:
    stripped = text.strip()
    if not stripped:
        return None
    if _BULLET_RE.match(stripped):
        return "bullet"
    if _ORDERED_RE.match(stripped):
        return "ordered"
    return None


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(_TOKEN_RE.findall(text)))


def _shared_prefix_len(left: Sequence[str], right: Sequence[str]) -> int:
    count = 0
    for l_word, r_word in zip(left, right):
        if l_word != r_word:
            break
        count += 1
    return count


def _chunk_hash(span_hashes: Sequence[str]) -> str:
    joined = "|".join(span_hashes)
    return blake2b(joined.encode("utf-8"), digest_size=16).hexdigest()


def _select_heading_path(blocks: Sequence[Dict[str, Any]]) -> List[str]:
    selected: List[str] = []
    for block in blocks:
        path = block.get("heading_path") or []
        if len(path) > len(selected):
            selected = list(path)
    return selected


def _fallback_heading_path(block: Dict[str, Any], heading_index: Dict[int, List[Dict[str, Any]]]) -> List[str]:
    page = block.get("page")
    if page is None:
        return []
    headings = heading_index.get(int(page)) or []
    if not headings:
        return []
    return [headings[-1]["title"]] if headings else []


__all__ = ["Chunk", "SmartChunker", "build_document_chunks"]
