"""Extractor for Instructions for Use documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List, Literal, Optional, Sequence, Tuple

from medparse.config import ExtractionConfig
from medparse.extract.references import extract_references
from medparse.extract.warnings_notes import extract_warning_blocks
from medparse.ingest.layout import SectionBoundary, collect_sections, iter_section_text
from medparse.ingest.pdf_reader import PageContent, iter_pages
from medparse.normalize.references import normalize_references
from medparse.types.base import EvidenceSpan, IFUWarning
from medparse.types.ifu import IFUDocument, IFUSectionEntry

Severity = Literal["warning", "caution", "note"]


def extract_ifu(pdf_path: Path, config: Optional[ExtractionConfig] = None) -> IFUDocument:
    """Extract structured IFU data."""
    config = config or ExtractionConfig()
    pages = list(iter_pages(pdf_path))
    sections = collect_sections(pages)
    metadata = _extract_metadata(pages, sections)
    warning_blocks = _prioritize_warnings(extract_warning_blocks(pages))
    grouped: dict[Severity, List[IFUWarning]] = {
        "warning": [],
        "caution": [],
        "note": [],
    }
    for block in warning_blocks:
        grouped.setdefault(block.severity, []).append(block)

    references = normalize_references(extract_references(pages))

    ifu = IFUDocument(
        doc_type="ifu",
        source_file=str(pdf_path),
        page_count=len(pages),
        references=[{"text": ref} for ref in references],
        **metadata,
    )

    for severity, items in grouped.items():
        for index, block in enumerate(items, start=1):
            block.id = block.id or ifu.stable_id(
                f"warning_{severity}", block.page, index, block.text[:80]
            )
            ifu.add_warning(block)

    total_warnings = len(ifu.warnings)

    if config.fail_fast and total_warnings == 0:
        raise ValueError("No warnings detected in IFU despite fail_fast=True.")

    return ifu


def _extract_metadata(
    pages: list[PageContent], sections: Sequence[SectionBoundary]
) -> dict[str, Any]:
    flat_lines = [line.strip() for page in pages for line in page.lines if line.strip()]

    indications_sentences = _extract_section_sentences(
        pages,
        sections,
        "Indications for Use",
        [
            "Intended Use",
            "Intended User",
            "Intended Patient Population",
            "Clinical Risks and Benefits",
        ],
    )
    intended_use_sentences = _extract_section_sentences(
        pages,
        sections,
        "Intended Use",
        [
            "Intended User",
            "Intended Patient Population",
            "Clinical Risks and Benefits",
            "Contraindications",
        ],
    )
    contraindication_sentences = _extract_section_sentences(
        pages,
        sections,
        "Contraindications",
        [
            "Warnings",
            "General Warnings, Cautions, and Notes",
            "Clinical Risks and Benefits",
        ],
    )
    intended_user_sentences = _extract_section_sentences(
        pages,
        sections,
        "Intended User",
        [
            "Clinical Risks and Benefits",
            "General Warnings, Cautions, and Notes",
            "Serious Incident Reporting",
        ],
    )

    seen_keys: set[str] = set()
    indications_entries = _build_section_entries(indications_sentences, "indication", seen_keys)
    intended_entries = _build_section_entries(intended_use_sentences, "intended_use", seen_keys)
    contraindications_entries = _build_section_entries(
        contraindication_sentences, "contraindication", seen_keys
    )

    metadata: dict[str, Any] = {
        "manufacturer": _find_manufacturer(flat_lines),
        "model": _find_model(flat_lines),
        "indications_for_use": indications_entries,
        "intended_use": intended_entries,
        "contraindications": contraindications_entries,
        "intended_user": _join_sentences(intended_user_sentences, limit=3),
    }

    return metadata


def _find_manufacturer(lines: list[str]) -> Optional[str]:
    for line in lines[:60]:
        lowered = line.lower()
        if "intuitive surgical" in lowered or "manufactured by" in lowered:
            return line.strip().rstrip(".,")
    return None


def _find_model(lines: list[str]) -> Optional[str]:
    for line in lines:
        if "model" in line.lower() and "system" in line.lower():
            match = re.search(r"model\s*([A-Z0-9-]+)", line, re.IGNORECASE)
            if match:
                model_code = match.group(1).upper()
                return f"Ion Endoluminal System Model {model_code}"
            return line.strip()
    return None


def _extract_section_sentences(
    pages: list[PageContent],
    sections: Sequence[SectionBoundary],
    title: str,
    end_titles: Sequence[str],
) -> List[Tuple[str, int]]:
    lines = iter_section_text(pages, sections, title, end_titles)
    sentences: List[Tuple[str, int]] = []
    buffer = ""
    sentence_page: Optional[int] = None

    for page_number, raw_line in lines:
        stripped = re.sub(r"\s+", " ", raw_line).strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if "user manual" in lowered or "rev." in lowered:
            continue
        if "|" in stripped and "introduction" in lowered:
            continue
        if re.match(r"^\d+\s", stripped):
            continue
        if lowered.startswith(title.lower()):
            continue

        fragments = re.split(r"(?<=[.!?])\s+", stripped)
        for fragment in fragments:
            fragment = fragment.strip()
            if not fragment:
                continue
            if not buffer:
                buffer = fragment
                sentence_page = page_number
            else:
                buffer += " " + fragment
            if fragment.endswith((".", "!", "?")):
                sentence = re.sub(r"\s+", " ", buffer).strip()
                sentence = re.sub(r"\s+\d+$", "", sentence)
                if sentence:
                    sentences.append((sentence, sentence_page or page_number))
                buffer = ""
                sentence_page = None

    if buffer:
        sentence = re.sub(r"\s+", " ", buffer).strip()
        sentence = re.sub(r"\s+\d+$", "", sentence)
        if sentence:
            fallback_page = sentence_page or (lines[-1][0] if lines else 1)
            sentences.append((sentence, fallback_page))

    return sentences


def _normalize_sentence_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _build_section_entries(
    sentences: List[Tuple[str, int]],
    prefix: str,
    seen_keys: set[str],
) -> List[IFUSectionEntry]:
    entries: List[IFUSectionEntry] = []
    counter = 1

    for sentence, page in sentences:
        if len(sentence.split()) < 4:
            continue
        key = _normalize_sentence_key(sentence)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        entries.append(
            IFUSectionEntry(
                id=f"{prefix}_{counter:03d}",
                text=sentence,
                evidence_spans=[EvidenceSpan(text=sentence, page=page)],
            )
        )
        counter += 1

    return entries


def _join_sentences(sentences: List[Tuple[str, int]], limit: int = 3) -> Optional[str]:
    if not sentences:
        return None
    texts = [sentence for sentence, _ in sentences[:limit]]
    joined = " ".join(texts).strip()
    joined = re.sub(r"\s+\d+$", "", joined)
    return joined or None


def _prioritize_warnings(blocks: List[IFUWarning]) -> List[IFUWarning]:
    if len(blocks) <= 40:
        return blocks

    keywords = {
        "laser",
        "saline",
        "suction",
        "pinch",
        "leakage",
        "catheter",
        "fluoroscopy",
        "biopsy",
        "accessory",
    }
    prioritized: List[IFUWarning] = []
    seen: set[str] = set()

    def add(block: IFUWarning) -> None:
        key = block.text.lower()
        if key in seen:
            return
        seen.add(key)
        prioritized.append(block)

    for block in blocks:
        if any(keyword in block.text.lower() for keyword in keywords):
            add(block)
            if len(prioritized) >= 40:
                break

    if len(prioritized) < 40:
        for block in blocks:
            if len(prioritized) >= 40:
                break
            add(block)

    return prioritized
