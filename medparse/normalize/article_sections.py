"""Article section extraction with column reflow and TOC exclusion."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from medparse.ingest.models import PageData
from medparse.normalize.layout import (
    detect_column_layout,
    is_toc_page,
    reflow_columns,
    slice_between,
)
from medparse.normalize.text_cleanup import clean_paragraph


# Standard article section anchors
SECTION_ANCHORS = {
    'abstract': ['abstract', 'summary'],
    'background': ['background', 'introduction', 'rationale'],
    'methods': ['methods', 'materials and methods', 'patients and methods', 'study design', 'study methodology', 'materials & methods'],
    'results': ['results', 'findings', 'outcomes'],
    'discussion': ['discussion', 'interpretation', 'comment', 'commentary'],
    'conclusion': ['conclusion', 'conclusions', 'summary'],
    'limitations': ['limitations', 'study limitations'],
    'funding': ['funding', 'financial support', 'grant support'],
    'conflicts': ['conflict of interest', 'conflicts of interest', 'disclosures'],
    'ethics': ['ethics', 'institutional review board', 'irb approval', 'ethics statement'],
}


def normalize_article_sections(pages: List[PageData]) -> Dict[str, str]:
    """Extract and normalize article sections with column awareness and TOC exclusion.

    Args:
        pages: Document pages

    Returns:
        Dictionary mapping section names to clean text
    """
    processed: List[PageData] = []
    for page in pages:
        layout = detect_column_layout(page)
        processed.append(reflow_columns(page) if layout > 1 else page)

    sections = {}

    # Extract each section
    for section_key, start_anchors in SECTION_ANCHORS.items():
        # Build stop anchors (all other section headings)
        all_anchors = [a for anchors in SECTION_ANCHORS.values() for a in anchors]
        stop_anchors = [a for a in all_anchors if a not in start_anchors]

        # Extract bounded section
        if section_key == 'abstract':
            raw_text = _extract_structured_abstract(processed)
        else:
            guard = None if section_key == 'abstract' else is_toc_page
            raw_text = slice_between(
                processed,
                start_anchors=start_anchors,
                stop_anchors=stop_anchors,
                guard_fn=guard,
                allow_inline_stop=False,
            )

        if raw_text:
            # Post-process: normalize whitespace, fix hyphenation
            clean_text = dehyphenate(raw_text)
            clean_text = clean_paragraph(clean_text)
            sections[section_key] = clean_text

    if 'methods' in sections and 'results' in sections and 'discussion' not in sections:
        synthetic = _synthesise_discussion(processed)
        if synthetic:
            sections['discussion'] = clean_paragraph(synthetic)

    return sections


def dehyphenate(text: str) -> str:
    """Fix end-of-line hyphenation (smart: only join if lowercase after hyphen).

    Args:
        text: Text with potential hyphenation artifacts

    Returns:
        Text with smart dehyphenation applied
    """
    # Pattern: word ending with hyphen, newline, then lowercase word
    # Only join if the next character is lowercase (not a new sentence)
    pattern = r'(\w)-\s*\n\s*([a-z])'
    text = re.sub(pattern, r'\1\2', text)

    return text


def find_first_occurrence_page(pages: List[PageData], anchors: List[str]) -> Optional[int]:
    """Find the first page (0-indexed) containing any of the anchors."""
    for idx, page in enumerate(pages):
        joined = "\n".join(page.lines).lower()
        if any(anchor.lower() in joined for anchor in anchors):
            return idx
    return None


def _extract_structured_abstract(pages: List[PageData]) -> str:
    """Extract structured abstract, preserving labelled subsections."""

    collecting = False
    lines: List[str] = []
    structured_labels = {
        "background",
        "objectives",
        "design",
        "methods",
        "results",
        "conclusions",
        "interpretation",
    }
    stop_markers = {"keywords", "abbreviations"}
    hard_section_markers = {
        "background",
        "introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
        "conclusions",
    }

    for page in pages:
        for raw_line in page.lines:
            line = raw_line.strip()

            if not line:
                if collecting and (lines and lines[-1] != ""):
                    lines.append("")
                continue

            lower = line.lower()

            if not collecting:
                if lower.startswith("abstract"):
                    collecting = True
                    remainder = line[len("Abstract") :].lstrip(": ").strip()
                    if remainder:
                        lines.append(remainder)
                    continue
            else:
                keyword_match = None
                for marker in stop_markers:
                    token = f"{marker}:"
                    idx = lower.find(token)
                    if idx != -1:
                        keyword_match = idx
                        break
                if keyword_match is not None:
                    if keyword_match > 0:
                        lines.append(line[:keyword_match].rstrip())
                    return "\n".join(lines).strip()

                if ":" in line:
                    label = lower.split(":", 1)[0]
                    if label in structured_labels:
                        lines.append(line)
                        continue

                if lower in hard_section_markers:
                    return "\n".join(lines).strip()

                if _looks_like_section_heading(line):
                    return "\n".join(lines).strip()

                lines.append(line)

    return "\n".join(lines).strip()


def _synthesise_discussion(pages: List[PageData]) -> str:
    tail_lines: List[str] = []
    for page in pages[-2:]:
        tail_lines.extend(page.lines or [])
    tail_text = "\n".join(tail_lines)
    match = re.search(
        r"(?:^|\n)(in conclusion|conclusions?|summary)[:\s]+(.+)",
        tail_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    snippet = match.group(0)
    snippet = re.split(r"\n\s*\n", snippet, maxsplit=1)[0]
    return snippet.strip()


def _looks_like_section_heading(line: str) -> bool:
    """Heuristic to detect the start of a new section outside the abstract."""

    if ":" in line:
        return False
    stripped = line.strip()
    if not stripped:
        return False
    words = stripped.split()
    if len(words) > 8:
        return False
    alpha_chars = [ch for ch in stripped if ch.isalpha()]
    if not alpha_chars:
        return False
    lowercase_token = stripped.lower()
    if lowercase_token in {
        "background",
        "introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
        "conclusions",
    }:
        return True
    uppercase_ratio = sum(1 for ch in alpha_chars if ch.isupper()) / len(alpha_chars)
    return stripped.isupper() or uppercase_ratio >= 0.7


__all__ = ["normalize_article_sections", "dehyphenate", "find_first_occurrence_page"]
