"""Figure and caption extraction with cross-references (shared for articles and textbooks)."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Dict, List, Optional

from pydantic import BaseModel

from medparse.ingest.models import PageData


class FigureBlock(BaseModel):
    """Figure with caption and metadata."""
    label: str  # e.g., "Figure 1", "Fig. 2a"
    caption: Optional[str] = None
    page: Optional[int] = None
    # bbox would require image detection - optional for now


def extract_figures_and_captions(pages: List[PageData]) -> List[FigureBlock]:
    """Extract figures with captions from pages.

    Args:
        pages: Document pages

    Returns:
        List of FigureBlock objects
    """
    figures: Dict[str, FigureBlock] = OrderedDict()

    for page in pages:
        page_text = '\n'.join(page.lines)

        # Find figure captions (start with "Figure X." or "Fig. X.")
        caption_pattern = r'(?:Figure|Fig\.?)\s+(\d+[a-z]?)[:\.]?\s+(.+?)(?=(?:Figure|Fig\.?)\s+\d+|\n\n|$)'
        matches = re.finditer(caption_pattern, page_text, re.IGNORECASE | re.DOTALL)

        for m in matches:
            fig_num = m.group(1)
            caption = m.group(2).strip()

            caption = _normalize_caption_text(clean_caption(caption))
            label = f"Figure {fig_num}"
            page_number = page.number if hasattr(page, "number") else None

            existing = figures.get(label)
            if existing is None:
                figures[label] = FigureBlock(
                    label=label,
                    caption=caption,
                    page=page_number,
                )
            else:
                merged = _merge_captions(existing.caption, caption)
                existing.caption = merged
                if existing.page is None and page_number is not None:
                    existing.page = page_number

    return list(figures.values())


def clean_caption(caption: str) -> str:
    """Remove trailing references, page numbers, etc. from caption.

    Args:
        caption: Raw caption text

    Returns:
        Cleaned caption
    """
    # Remove trailing citations like "[12]"
    caption = re.sub(r'\[\d+\]$', '', caption)

    # Truncate at terminal punctuation if very long
    if len(caption) > 500:
        sentences = re.split(r'(?<=[.!?])\s+', caption)
        caption = '. '.join(sentences[:3])
        if not caption.endswith('.'):
            caption += '.'

    # Remove common artifacts
    caption = re.sub(r'\s+Page\s+\d+', '', caption, flags=re.IGNORECASE)
    caption = re.sub(r'\s+\d+\s*$', '', caption)

    return caption.strip()


def _normalize_caption_text(caption: str) -> str:
    if not caption:
        return caption
    caption = caption.replace('-\n', '')
    caption = re.sub(r'\s+', ' ', caption)
    caption = caption.replace('..', '.')
    caption = re.sub(r'\.(\s*\.)+', '.', caption)
    return caption.strip()


def _merge_captions(existing: Optional[str], incoming: Optional[str]) -> Optional[str]:
    if not existing:
        return incoming
    if not incoming:
        return existing
    segments: List[str] = []
    for candidate in (existing, incoming):
        if not candidate:
            continue
        parts = [part.strip() for part in re.split(r'\s{2,}|\n', candidate) if part.strip()]
        for part in parts:
            if part not in segments:
                segments.append(part)
    return ' '.join(segments)


def link_figure_references(
    sections: Dict[str, str],
    figures: List[FigureBlock]
) -> Dict[str, List[str]]:
    """Back-link in-text figure references to figure IDs.

    Args:
        sections: Document sections (dict of section_name -> text)
        figures: Extracted figures

    Returns:
        Dictionary mapping section names to lists of referenced figure labels
    """
    references = {}

    for section_key, section_text in sections.items():
        refs = []

        for fig in figures:
            # Extract figure number from label (e.g., "1" from "Figure 1")
            fig_num = fig.label.split()[-1]

            # Look for references like "(Fig. 1)", "Figure 1", "(see Fig. 1)"
            patterns = [
                rf'\((?:Fig\.|Figure)\s*{re.escape(fig_num)}\)',
                rf'Figure\s+{re.escape(fig_num)}\b',
                rf'see\s+(?:Fig\.|Figure)\s*{re.escape(fig_num)}\b'
            ]

            for pattern in patterns:
                if re.search(pattern, section_text, re.IGNORECASE):
                    refs.append(fig.label)
                    break

        if refs:
            references[section_key] = refs

    return references


__all__ = [
    "extract_figures_and_captions",
    "link_figure_references",
    "FigureBlock",
    "clean_caption",
]
