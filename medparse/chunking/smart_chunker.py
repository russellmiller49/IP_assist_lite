"""Layout-aware chunking utilities for RAG-friendly payloads."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from hashlib import blake2b
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from medparse.ingest.models import Heading, PageData
from medparse.text.hash import normalize_paragraph_text
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
    content_hashes: List[str] = field(default_factory=list)
    token_len: int = 0
    anchors: List[str] = field(default_factory=list)
    safety_level: Optional[str] = None
    column_id: Optional[int] = None
    section_ordinal: int = 0
    text: str = ""
    method: str = "smart"
    overlap_prev: bool = False
    overlap_next: bool = False


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
                    chunk = buffer.finalize(len(chunks))
                    chunks.append(chunk)
                buffer = _ChunkBuffer(self)

            if (
                block_type != "table"
                and buffer
                and buffer.token_len
                and buffer.token_len + block_tokens > self.token_max
            ):
                chunk = buffer.finalize(len(chunks))
                chunks.append(chunk)
                buffer = _ChunkBuffer(self)

            if buffer.should_break(block):
                chunk = buffer.finalize(len(chunks))
                chunks.append(chunk)
                buffer = _ChunkBuffer(self)

            buffer.add(block)

            # Tables are kept intact, but safety blocks should respect token limits
            if block_type == "table":
                continue

            if buffer.token_len >= self.token_max:
                exceeds_list = buffer.list_mode is not None
                chunk = buffer.finalize(len(chunks))
                next_buffer = _ChunkBuffer(self) if exceeds_list else buffer.bootstrap_with_overlap()
                if not exceeds_list and self.overlap_ratio > 0 and next_buffer:
                    chunk.overlap_next = True
                chunks.append(chunk)
                buffer = next_buffer

        if buffer:
            chunk = buffer.finalize(len(chunks))
            chunks.append(chunk)

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
        self.overlap_from_previous: bool = False

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
        content_hashes = [block["content_hash"] for block in self.blocks if block.get("content_hash")]
        if not content_hashes:
            content_hashes = list(span_hashes)
        pages = sorted({int(block.get("page") or 0) for block in self.blocks if block.get("page")})
        heading_path = _select_heading_path(self.blocks) or self.heading_path
        text_parts = [str(block.get("text") or "").strip() for block in self.blocks]
        chunk_text = "\n\n".join([part for part in text_parts if part]) or ""
        chunk = Chunk(
            id=f"chunk_{index + 1:04d}",
            hash=_provisional_chunk_hash(content_hashes, pages or []),
            type=self.chunk_type or "text",
            heading_path=heading_path,
            page_range=pages or [],
            span_hashes=span_hashes,
            content_hashes=content_hashes,
            token_len=self.token_len,
            anchors=list(self.anchors or []),
            safety_level=self.safety_level,
            column_id=self.column_id,
            section_ordinal=0,
            text=chunk_text,
            method="smart",
            overlap_prev=bool(self.overlap_from_previous),
            overlap_next=False,
        )
        return chunk

    def bootstrap_with_overlap(self) -> "_ChunkBuffer":
        if not self.blocks or self.chunker.overlap_ratio <= 0:
            return _ChunkBuffer(self.chunker)
        overlap_size = max(1, int(len(self.blocks) * self.chunker.overlap_ratio))
        overlap_blocks = self.blocks[-overlap_size:]
        new_buffer = _ChunkBuffer(self.chunker)
        for block in overlap_blocks:
            new_buffer.add(block)
        new_buffer.overlap_from_previous = True
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
        payload["content_hash"] = block.get("content_hash")
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
    column_mode = str(settings.get("column_mode", "off") or "off").lower()
    column_sort_enabled = column_mode == "auto"
    blocks, heading_index = _build_blocks(
        paragraph_store,
        pages,
        anchor_spans=anchor_spans,
        safety_headers=safety_headers,
        tables=tables_index,
        max_tokens=int(settings.get("token_max", 500) or 500),
        column_sort=column_sort_enabled,
    )

    if not blocks:
        return [], {"enabled": False, "reason": "no_blocks", "mode": mode}

    base_token_min = int(settings.get("token_min", 200) or 200)
    token_max = int(settings.get("token_max", 500) or 500)
    overlap_ratio = float(settings.get("overlap_ratio", 0.15) or 0.15)
    enable_c99 = bool(settings.get("enable_c99", False))
    max_chunks_per_doc = int(settings.get("max_chunks_per_doc") or 0)
    min_merge_threshold = int(settings.get("min_tokens_merge_threshold") or 0)
    page_count = len(pages) if pages is not None else 0

    def _run_chunk_cycle(token_min_value: int) -> Tuple[List[Dict[str, Any]], SmartChunker, int, int, int]:
        chunker_local = SmartChunker(
            token_min=token_min_value,
            token_max=token_max,
            overlap_ratio=overlap_ratio,
            enable_c99=enable_c99,
        )
        chunk_models = chunker_local.from_blocks(blocks, heading_index, safety_headers, tables_index)
        if not chunk_models:
            return [], chunker_local, 0, 0, 0
        _assign_provisional_hashes(chunk_models)
        unique_models, deduped_count = _deduplicate_chunk_models(chunk_models)
        _assign_chunk_identities(unique_models)
        serialized_models = _serialize_chunk_models(unique_models, mode)
        return serialized_models, chunker_local, len(chunk_models), len(unique_models), deduped_count

    deduped_chunks, chunker, created_count, unique_count, dedup_removed = _run_chunk_cycle(base_token_min)
    if not deduped_chunks:
        return [], {"enabled": False, "mode": mode, "reason": "no_chunks"}

    policy = "standard"
    truncated_count = 0
    merge_token_min = max(base_token_min, min_merge_threshold) if min_merge_threshold else base_token_min
    if max_chunks_per_doc > 0 and unique_count > max_chunks_per_doc and merge_token_min > chunker.token_min:
        deduped_chunks, chunker, created_count, unique_count, dedup_removed = _run_chunk_cycle(merge_token_min)
        policy = "bounded"
    post_dedup_count = unique_count
    emitted_chunks = list(deduped_chunks)
    if max_chunks_per_doc > 0 and post_dedup_count > max_chunks_per_doc:
        policy = "bounded"
        truncated_count = post_dedup_count - max_chunks_per_doc
        emitted_chunks = emitted_chunks[:max_chunks_per_doc]

    for idx, chunk in enumerate(emitted_chunks, start=1):
        chunk["id"] = f"chunk_{idx:04d}"

    avg_tokens = float(sum(chunk.get("token_len", 0) for chunk in emitted_chunks) / len(emitted_chunks)) if emitted_chunks else 0.0
    chunks_emitted = len(emitted_chunks)
    chunks_per_page = round(chunks_emitted / page_count, 3) if page_count else round(float(chunks_emitted), 3)
    unique_hash_ratio = round(post_dedup_count / created_count, 4) if created_count else 0.0

    metrics = {
        "enabled": True,
        "mode": mode,
        "chunks_created": created_count,
        "chunks_unique": post_dedup_count,
        "chunks_deduped": dedup_removed,
        "chunks_emitted": chunks_emitted,
        "chunks_truncated": truncated_count,
        "dedup_applied": created_count != post_dedup_count,
        "policy": policy,
        "chunks_per_page": chunks_per_page,
        "unique_hash_ratio": unique_hash_ratio,
        "avg_tokens": round(avg_tokens, 2),
        "token_min": chunker.token_min,
        "token_max": chunker.token_max,
        "overlap_ratio": chunker.overlap_ratio,
        "max_chunks_per_doc": max_chunks_per_doc,
    }
    return emitted_chunks, metrics


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
    column_sort: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[int, List[Dict[str, Any]]]]:
    heading_map = _build_heading_index(pages)
    page_offsets = _page_line_offsets(pages)
    occurrences = _iter_occurrences(paragraph_store, sort_by_column=column_sort)

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
        block["content_hash"] = _block_content_hash(block["text"])
        if max_tokens and block["token_len"] > max_tokens:
            blocks.extend(_split_block(block, max_tokens))
        else:
            blocks.append(block)

    return blocks, heading_map


def _iter_occurrences(
    store: Dict[str, Dict[str, Any]],
    *,
    sort_by_column: bool = False,
) -> List[Dict[str, Any]]:
    occurrences: List[Tuple[Tuple[int, ...], Dict[str, Any]]] = []
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
            raw_order = orders[idx] if idx < len(orders) else orders[-1]
            try:
                order = int(raw_order)
            except (TypeError, ValueError):
                order = idx
            page_value = occurrence.get("page")
            try:
                page = int(page_value)
            except (TypeError, ValueError):
                page = 0
            char_span = occurrence.get("char_span") or []
            if isinstance(char_span, (list, tuple)) and char_span:
                try:
                    char_pos = int(char_span[0])
                except (TypeError, ValueError):
                    char_pos = idx
            else:
                char_pos = idx
            payload = {
                "order": order,
                "page": occurrence.get("page"),
                "char_span": occurrence.get("char_span"),
                "span_hash": span_hash,
                "text": entry.get("text"),
            }
            column_id = occurrence.get("column_id")
            if column_id is None:
                candidate = entry.get("column_id")
                if isinstance(candidate, int):
                    column_id = candidate
            if column_id is not None:
                payload["column_id"] = column_id
            if sort_by_column:
                column_key = column_id if column_id is not None else 0
                sort_key = (page, column_key, char_pos, order, idx, span_hash or "")
            else:
                sort_key = (page, char_pos, order, idx, span_hash or "")
            occurrences.append((sort_key, payload))
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
    """Split an oversized block into segments capped by ``max_tokens``, splitting the text content."""
    
    text = block.get("text") or ""
    if not text:
        return [block]
    
    # Tokenize the text to find split points
    tokens = _TOKEN_RE.findall(text)
    total_tokens = len(tokens)
    
    if total_tokens <= max_tokens:
        return [block]
    
    segments: List[Dict[str, Any]] = []
    base_span_hash = block.get("span_hash") or ""
    
    # Split into segments of approximately max_tokens each
    for idx in range(0, total_tokens, max_tokens):
        segment_tokens = tokens[idx:idx + max_tokens]
        segment_text = " ".join(segment_tokens)
        segment_token_len = len(segment_tokens)
        
        # Create a new segment with split text and unique span_hash
        segment = dict(block)
        segment["text"] = segment_text
        segment["token_len"] = segment_token_len
        segment["span_hash"] = f"{base_span_hash}_seg{idx // max_tokens}" if base_span_hash else f"seg{idx // max_tokens}"
        segment["segment_index"] = idx // max_tokens
        segment["content_hash"] = _block_content_hash(segment_text)
        segments.append(segment)
    
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


def _block_content_hash(text: str) -> str:
    normalized = normalize_paragraph_text(text)
    return blake2b(normalized.encode("utf-8"), digest_size=8).hexdigest()


def _chunk_identity_sort_key(chunk: Chunk) -> Tuple[int, int, Tuple[str, ...], Tuple[str, ...], int, str]:
    pages = list(chunk.page_range or [])
    start = pages[0] if pages else 0
    end = pages[-1] if pages else start
    spans = tuple(chunk.content_hashes or [])
    anchors = tuple(chunk.anchors or [])
    column = chunk.column_id if isinstance(chunk.column_id, int) else -1
    chunk_type = chunk.type or "text"
    return (start, end, spans, anchors, column, chunk_type)


def _assign_chunk_identities(chunks: Sequence[Chunk]) -> None:
    """Assign section ordinals and stable hashes for each chunk."""

    buckets: Dict[Tuple[str, ...], List[Chunk]] = defaultdict(list)
    for chunk in chunks:
        heading_key = tuple(chunk.heading_path) if chunk.heading_path else ("__root__",)
        buckets[heading_key].append(chunk)

    for heading_key, bucket in buckets.items():
        ordered_bucket = sorted(bucket, key=_chunk_identity_sort_key)
        for ordinal, chunk in enumerate(ordered_bucket):
            chunk.section_ordinal = ordinal
            chunk.hash = _chunk_hash(chunk.content_hashes, chunk.page_range, ordinal)


def _assign_provisional_hashes(chunks: Sequence[Chunk]) -> None:
    for chunk in chunks:
        chunk.hash = _provisional_chunk_hash(chunk.content_hashes, chunk.page_range)


def _chunk_hash(span_hashes: Sequence[str], page_range: Sequence[int], ordinal: int) -> str:
    spans = list(span_hashes or [])
    pages = list(page_range or [])
    start = pages[0] if pages else 0
    end = pages[-1] if pages else start
    basis = "|".join(spans)
    basis = f"{basis}|{start}-{end}|{ordinal}"
    return blake2b(basis.encode("utf-8"), digest_size=16).hexdigest()


def _provisional_chunk_hash(span_hashes: Sequence[str], page_range: Sequence[int]) -> str:
    spans = [span for span in span_hashes or [] if span]
    if spans:
        basis = "|".join(spans)
    else:
        pages = [str(page) for page in page_range or [] if page is not None]
        basis = "|".join(pages) if pages else "chunk"
    return blake2b(basis.encode("utf-8"), digest_size=16).hexdigest()


def _deduplicate_chunk_models(chunks: Sequence[Chunk]) -> Tuple[List[Chunk], int]:
    unique: List[Chunk] = []
    seen: Dict[str, int] = {}
    duplicates = 0
    for chunk in chunks:
        digest = chunk.hash
        if digest and digest in seen:
            duplicates += 1
            continue
        if digest:
            seen[digest] = len(unique)
        unique.append(chunk)
    return unique, duplicates


def _serialize_chunk_models(chunk_models: Sequence[Chunk], mode: str) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunk_models, start=1):
        payload.append(
            {
                "id": f"chunk_{idx:04d}",
                "hash": chunk.hash,
                "type": chunk.type,
                "heading_path": list(chunk.heading_path),
                "page_range": list(chunk.page_range),
                "spans": list(chunk.span_hashes),
                "token_len": chunk.token_len,
                "anchors": list(chunk.anchors),
                "safety_level": chunk.safety_level,
                "text": chunk.text,
                "method": chunk.method or mode,
                "overlap_prev": bool(chunk.overlap_prev),
                "overlap_next": bool(chunk.overlap_next),
            }
        )
    return payload


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
