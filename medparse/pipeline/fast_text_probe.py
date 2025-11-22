"""Fast heuristic to detect PDFs with an embedded text layer."""

from __future__ import annotations

from pathlib import Path

TEXT_THRESHOLD = 50
PAGES_TO_SCAN = 2


def fast_text_probe(pdf_path: Path, *, max_pages: int = PAGES_TO_SCAN, char_threshold: int = TEXT_THRESHOLD) -> bool:
    """Return ``True`` when the PDF exposes readable text on the first few pages.

    The heuristic intentionally keeps the thresholds low so that any signal of selectable
    text routes the document through the Medparse (v6) path instead of Docling+OCR.
    """

    try:
        import fitz  # type: ignore[import-untyped]
    except Exception:
        # If PyMuPDF is unavailable we optimistically assume the PDF has text.
        return True

    document = None
    try:
        document = fitz.open(pdf_path)  # type: ignore[arg-type]
    except Exception:
        return False

    try:
        page_total = max(0, int(getattr(document, "page_count", 0) or 0))
        pages_to_check = min(max_pages, page_total or max_pages)
        for index in range(pages_to_check):
            try:
                page = document.load_page(index)
            except Exception:
                continue
            text = page.get_text("text") or ""
            if len(text) >= char_threshold:
                return True
        return False
    finally:
        try:
            document.close()
        except Exception:
            pass


__all__ = ["fast_text_probe"]
