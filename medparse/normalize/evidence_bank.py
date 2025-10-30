"""Helpers for deduplicating paragraphs and emitting evidence references."""

from __future__ import annotations

import hashlib
import re
from typing import Dict, MutableMapping, Optional, Tuple

from medparse.schema.common import EvidenceSpan

ParagraphEntry = Dict[str, object]
ParagraphStore = MutableMapping[str, ParagraphEntry]


def _normalize_paragraph(text: str) -> str:
    return " ".join(text.split())


def register_paragraph(
    store: ParagraphStore,
    paragraph_index: Optional[int],
    text: Optional[str],
    page: Optional[int] = None,
) -> Optional[str]:
    """Insert ``text`` into ``store`` keyed by normalized hash and return hash."""

    if not text:
        return None
    normalized = _normalize_paragraph(text)
    if not normalized:
        return None

    hash_id = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    entry = store.get(hash_id)
    if entry is None or not isinstance(entry, dict):
        entry = {"text": text.strip()}
        store[hash_id] = entry
    elif not entry.get("text"):
        entry["text"] = text.strip()
    elif len(text.strip()) > len(str(entry.get("text", ""))):
        entry["text"] = text.strip()

    if page is not None:
        pages = entry.setdefault("pages", [])
        if isinstance(pages, list) and page not in pages:
            pages.append(page)

    if paragraph_index is not None:
        order = entry.setdefault("order", [])
        if isinstance(order, list) and paragraph_index not in order:
            order.append(paragraph_index)

    entry["length"] = len(str(entry.get("text", "")))
    return hash_id


def span_to_ref(span: EvidenceSpan, store: ParagraphStore) -> Optional[Dict[str, object]]:
    """Convert an ``EvidenceSpan`` into a reference payload."""

    if not isinstance(span, EvidenceSpan):
        return None

    hash_id = span.hash or span.compute_hash()
    paragraph_hash = span.paragraph_hash or hash_id
    entry = store.get(paragraph_hash)
    entry_text = ""
    if isinstance(entry, dict):
        entry_text = str(entry.get("text") or "")

    start, end = (None, None)
    if span.paragraph_offset:
        start, end = span.paragraph_offset
    elif entry_text:
        start, end = 0, len(entry_text)
    elif span.text:
        start, end = 0, len(span.text)

    ref: Dict[str, object] = {
        "hash": hash_id,
        "paragraph_hash": paragraph_hash,
    }

    page = span.page
    if page is None and isinstance(entry, dict):
        pages = entry.get("pages")
        if isinstance(pages, list) and pages:
            page = pages[0]
    if page is not None:
        ref["page"] = page

    if start is not None and end is not None:
        ref["start"] = int(start)
        ref["end"] = int(end)

    snippet_limit = 280

    snippet: Optional[str] = None
    if entry_text:
        snippet_start = start if start is not None else 0
        snippet_end = end if end is not None else len(entry_text)
        snippet = entry_text[snippet_start:snippet_end]
    elif span.text:
        snippet = span.text

    if snippet:
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if snippet:
            lowered = snippet.lower()
            if lowered.startswith("page ") and "window" in lowered:
                snippet = ""
            if lowered.startswith("window<="):
                snippet = ""
        if snippet:
            if len(snippet) > snippet_limit:
                snippet = snippet[:snippet_limit].rstrip() + "…"
                ref["truncated"] = True
            ref["snippet"] = snippet

    if span.truncated:
        ref["truncated"] = True

    if span.confidence is not None:
        ref["confidence"] = span.confidence

    if span.bbox:
        ref["bbox"] = span.bbox

    return ref


__all__ = ["register_paragraph", "span_to_ref", "ParagraphStore", "ParagraphEntry"]
