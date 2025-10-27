"""Enhanced IFU extraction with post-processing hardening."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from medparse.config import ExtractionConfig, get_extraction_config

from medparse.extract.utils import (
    collect_lines,
    collect_tables,
    iter_section_windows,
    load_pages,
    reference_section,
    section_text_between,
)
from medparse.ingest.models import PageData
from medparse.normalize.ifu_anchors import lift_ifu_clinical_fields
from medparse.normalize.ifu_frontmatter import parse_front_matter
from medparse.normalize.page_furniture import strip_furniture
from medparse.normalize.references import gate_ifu_references, normalize_references
from medparse.normalize.safety import categorize_block, dedupe_blocks, detect_severity
from medparse.normalize.software import filter_software_versions
from medparse.normalize.tables import clean_tables
from medparse.normalize.text_cleanup import clean_paragraph, deep_cleanup_fields
from medparse.schema.common import EvidenceSpan
from medparse.schema.ifu import IFUDocument, SafetyBlock

SECTION_FIELDS = {
    "indications for use": "indications_for_use",
    "intended use": "intended_use",
    "intended user": "intended_user",
    "intended patient population": "intended_patient_population",
    "contraindications": "contraindications",
    "adverse events": "adverse_events",
}


def extract_ifu(
    pdf_path: Path,
    *,
    engine: str = "pymupdf",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
    config: Optional[ExtractionConfig] = None,
) -> IFUDocument:
    """Extract an IFU document with hardened normalization."""

    extraction_config = config or get_extraction_config()
    pages = pages or load_pages(pdf_path, engine=engine, max_pages=page_limit)
    page_count = len(pages)

    # Strip page furniture (headers/footers) before processing
    lines_by_page = [page.lines for page in pages]
    clean_lines_by_page = strip_furniture(lines_by_page, threshold=0.6)

    # Update pages with cleaned lines and rebuild text
    for page, clean_lines in zip(pages, clean_lines_by_page):
        page.lines = clean_lines
        page.text = '\n'.join(clean_lines)

    lines = collect_lines(pages)
    pages_text = [page.text for page in pages]

    section_text: dict[str, str] = {}
    for heading, next_heading in iter_section_windows(pages):
        text, _evidence, _ = section_text_between(pages, heading, next_heading)
        section_text[heading.title.lower()] = text

    doc_kwargs: dict[str, object] = {
        "doc_type": "ifu",
        "source_file": str(pdf_path),
        "page_count": page_count,
        "manufacturer": None,
        "product_name": None,
        "part_number": None,
        "revision": None,
        "publication_date": None,
        "model": None,
        "software_versions": [],
        "tables": collect_tables(pages),
        "references": normalize_references(
            reference_section(lines),
            mode="ifu",
            headings=[heading.title for page in pages for heading in page.headings],
        ),
        "safety_blocks": _extract_safety_blocks(pages),
    }

    for key, field in SECTION_FIELDS.items():
        if key in section_text:
            doc_kwargs[field] = section_text[key]

    lift_ifu_clinical_fields(pages_text, doc_kwargs, pdf_path=pdf_path)

    meta = parse_front_matter(pages_text)

    # Collect software versions from Equipment/Software Version section
    raw_software: List[str] = []
    for page_idx, page_text in enumerate(pages_text[:10]):  # Check first 10 pages
        # Look for Equipment and Software Version section
        if "equipment" in page_text.lower() and "software" in page_text.lower():
            # Extract lines that mention Ion OS or PlanPoint
            for line in page_text.splitlines():
                if "ion" in line.lower() and "os" in line.lower():
                    raw_software.append(line.strip())
                elif "planpoint" in line.lower():
                    raw_software.append(line.strip())

    for key in (
        "part_number",
        "revision",
        "publication_date",
        "model",
        "manufacturer",
        "product_name",
    ):
        value = meta.get(key)
        if value:
            doc_kwargs[key] = value

    # Apply text cleanup to narrative fields
    for fld in ("product_name", "indications_for_use", "intended_use",
                "intended_user", "intended_patient_population"):
        val = doc_kwargs.get(fld)
        if isinstance(val, str) and val:
            doc_kwargs[fld] = clean_paragraph(val)

    if extraction_config.is_enriched():
        deep_cleanup_fields(doc_kwargs)
        doc_kwargs["tables"] = clean_tables(doc_kwargs.get("tables", []))
        doc_kwargs["software_versions"] = filter_software_versions(raw_software)
        doc_kwargs["safety_blocks"] = dedupe_blocks(doc_kwargs.get("safety_blocks", []))
        gate_ifu_references(doc_kwargs, pages_text)
    else:
        doc_kwargs["tables"] = doc_kwargs.get("tables", [])
        doc_kwargs["software_versions"] = raw_software

    # Ensure list defaults
    for key in ("contraindications", "adverse_events"):
        if not doc_kwargs.get(key):
            doc_kwargs[key] = []

    return IFUDocument.model_validate(doc_kwargs)


def _extract_safety_blocks(pages: List[PageData]) -> List[SafetyBlock]:
    blocks: List[SafetyBlock] = []
    for page in pages:
        heading_lookup = _page_heading_lookup(page)
        idx = 0
        while idx < len(page.lines):
            line = page.lines[idx].strip()
            severity = detect_severity(line)
            if not severity:
                idx += 1
                continue

            text_lines = [line]
            j = idx + 1
            while j < len(page.lines):
                next_line = page.lines[j].strip()
                if not next_line:
                    break
                if detect_severity(next_line):
                    break
                text_lines.append(next_line)
                j += 1

            block_text = " ".join(text_lines)
            parent_heading = heading_lookup(idx)
            category = categorize_block(block_text, parent_heading=parent_heading)
            evidence = EvidenceSpan(text=block_text[:200], page=page.number, bbox=None, confidence=0.8)
            blocks.append(
                SafetyBlock(
                    severity=severity,  # type: ignore[arg-type]
                    text=block_text,
                    category=category,
                    evidence=evidence,
                )
            )
            idx = j
    return blocks


def _page_heading_lookup(page: PageData):
    heading_lines = sorted(
        [
            (heading.line_index, heading.title)
            for heading in page.headings
            if heading.kind == "section"
        ],
        key=lambda item: item[0],
    )

    def lookup(line_index: int) -> str | None:
        candidates = [title for idx, title in heading_lines if idx <= line_index]
        return candidates[-1] if candidates else None

    return lookup


__all__ = ["extract_ifu"]
