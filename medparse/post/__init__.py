"""Post-processing utilities for Docling-based ingests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Sequence

from medparse.ingest.tables import ensure_tables
from medparse.layout.reflow import Block, reflow_page
from medparse.processing import DoclingProcessor
from medparse.text.hygiene import normalize_text

_PROCESSOR = DoclingProcessor()


def postprocess_docling(
    conversion_result: Any,
    *,
    doc_type: str,
    doc_id: str,
    source_pdf: Path,
):
    """Apply layout-aware cleanup before serializing Docling output."""

    document = getattr(conversion_result, "document", None)
    if document is None:
        raise RuntimeError("Docling conversion produced no document")

    _apply_layout_normalization(document)
    result = _PROCESSOR.process(document, doc_id=doc_id, doc_type=doc_type)
    result = ensure_tables(result, source_pdf)
    return result


def _apply_layout_normalization(document: Any) -> None:
    pages = _safe_list(getattr(document, "pages", None))
    if not pages:
        return
    for page in pages:
        blocks = _safe_list(getattr(page, "blocks", None))
        if not blocks:
            continue
        page_no = _resolve_page_number(page)
        page_height = _resolve_page_height(page)
        block_models: List[tuple[Block, Any]] = []
        for block in blocks:
            text = _extract_block_text(block)
            bbox = _extract_block_bbox(block)
            if not text or not bbox:
                continue
            block_models.append((Block(text=text, bbox=bbox, page=page_no), block))
        if not block_models:
            continue
        ordered = reflow_page([model for model, _ in block_models], page_height)
        if not ordered:
            continue
        id_map = {id(model): original for model, original in block_models}
        reordered = []
        for model in ordered:
            original = id_map.get(id(model))
            if original is None:
                continue
            cleaned = normalize_text(model.text or "")
            _set_block_text(original, cleaned)
            reordered.append(original)
        try:
            page.blocks = reordered
        except Exception:
            # Some Docling objects expose pages as tuples; fall back to in-place mutation.
            for idx, block in enumerate(reordered):
                try:
                    blocks[idx] = block
                except Exception:
                    break


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _resolve_page_number(page: Any) -> int:
    for attr in ("page_no", "number", "page_number", "index"):
        value = getattr(page, attr, None)
        if isinstance(value, int) and value > 0:
            return value
    return 1


def _resolve_page_height(page: Any) -> float:
    size = getattr(page, "size", None)
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        try:
            return float(size[1])
        except (TypeError, ValueError):
            return 0.0
    height = getattr(page, "height", None)
    try:
        return float(height)
    except (TypeError, ValueError):
        return 0.0


def _extract_block_text(block: Any) -> str:
    for attr in ("text", "content", "value"):
        text = getattr(block, attr, None)
        if isinstance(text, str) and text.strip():
            return text
    return ""


def _extract_block_bbox(block: Any) -> tuple[float, float, float, float] | None:
    bbox = getattr(block, "bbox", None) or getattr(block, "bounding_box", None)
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        try:
            return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        except (TypeError, ValueError):
            return None
    if isinstance(bbox, dict):
        try:
            return (
                float(bbox.get("x0", 0.0)),
                float(bbox.get("y0", 0.0)),
                float(bbox.get("x1", 0.0)),
                float(bbox.get("y1", 0.0)),
            )
        except (TypeError, ValueError):
            return None
    return None


def _set_block_text(block: Any, text: str) -> None:
    if hasattr(block, "text"):
        setattr(block, "text", text)
    elif hasattr(block, "content"):
        setattr(block, "content", text)
    elif hasattr(block, "value"):
        setattr(block, "value", text)


__all__ = ["postprocess_docling"]
