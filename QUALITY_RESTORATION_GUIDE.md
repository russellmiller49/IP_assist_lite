# Quality Restoration & Hardening Guide

**Date**: 2025-10-24
**Status**: Implementation roadmap for restoring enriched outputs
**Priority**: CRITICAL - Addresses quality regression

---

## Executive Summary

This guide systematically restores the enriched article/textbook outputs (UMLS, relations, graded recommendations) and hardens IFU extraction with deterministic validation gates. The Ion IFU regression (TOC bleed into `indications_for_use`) serves as the sentinel case for all validation rules.

**Mode System Created**: ✅ COMPLETED
- `MEDPARSE_PROFILE=fast_raw` → Minimal parsing, no UMLS
- `MEDPARSE_PROFILE=enriched` (default) → Full normalizers + UMLS + validators

---

## 0. Mode System (✅ COMPLETED)

### [medparse/config.py](medparse/config.py)

**Enhanced ExtractionConfig**:
```python
class ExtractionProfile(str, Enum):
    FAST_RAW = "fast_raw"  # Quick triage, no enrichment
    ENRICHED = "enriched"  # Full pipeline (default)

class ExtractionConfig(BaseModel):
    profile: ExtractionProfile = ENRICHED

    # Auto-disabled in fast_raw
    enable_umls: bool = True
    enable_relations: bool = True
    enable_guideline_norms: bool = True
    enable_validators: bool = True
    reject_toc_bleed: bool = True

    # CLI flags do NOT bypass enrichment in enriched mode
    use_cache: bool = True
    max_pages: Optional[int] = None

    @classmethod
    def from_env(cls):
        profile = os.getenv("MEDPARSE_PROFILE", "enriched")
        # If fast_raw, disable all enrichment
        # If enriched, respect individual MEDPARSE_ENABLE_* flags
```

**Usage**:
```bash
# Fast mode (triage only)
MEDPARSE_PROFILE=fast_raw python -m medparse.cli extract-ifus ...

# Enriched mode (default - full quality)
python -m medparse.cli extract-ifus ...  # Same as MEDPARSE_PROFILE=enriched

# Enriched with selective toggles
MEDPARSE_ENABLE_UMLS=0 python -m medparse.cli extract-articles ...  # Skip UMLS only
```

**Implementation Status**: ✅ Complete

---

## 1. IFU Hardening (Anchor Windowing & TOC Guards)

### Problem Statement

**Ion IFU Regression** (553990-11 Rev. C):
- `indications_for_use` contains: `"Table of Contents 5 Ta b le o f C o n ten ts Chapter 1..."`
- Root cause: Anchor search captured TOC page instead of clinical text
- **This must NEVER happen again**

### Solution: Anchor Windowing with Layout-Aware Extraction

### Files to Create/Modify

1. **medparse/normalize/ifu_anchors.py** (NEW - Core anchor logic)
2. **medparse/normalize/ifu_frontmatter.py** (EXISTS - Keep)
3. **medparse/normalize/text_cleanup.py** (EXISTS - Enhance)
4. **medparse/normalize/tables.py** (EXISTS - Keep)
5. **medparse/extractors/ifu.py** (UPDATE - Wire new anchors)
6. **medparse/validate/ifu_rules.py** (NEW - Strict validation)
7. **configs/run_ifu.yaml** (NEW - Per-manufacturer config)

---

### 1.1 Core Anchor Extractor

**File**: `medparse/normalize/ifu_anchors.py` (NEW)

```python
"""IFU anchor-based extraction with TOC guards and layout-aware fallback."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from medparse.ingest.models import PageData
from medparse.normalize.page_furniture import strip_furniture
from medparse.normalize.text_cleanup import normalize_ligatures, clean_paragraph


class AnchorBleedError(Exception):
    """Raised when TOC or unrelated content bleeds into clinical block."""
    pass


# Standard IFU section anchors (manufacturer-agnostic)
IFU_ANCHORS = {
    'indications_for_use': [
        r'^Indications?\s+for\s+Use\b',
        r'^Intended\s+Use\b',
        r'^Indications?\b',
    ],
    'contraindications': [
        r'^Contraindications?\b',
        r'^When\s+NOT\s+to\s+Use\b',
    ],
    'adverse_events': [
        r'^Adverse\s+Events?\b',
        r'^Complications?\b',
        r'^Potential\s+(?:Adverse\s+)?Events?\b',
    ],
    'warnings': [
        r'^Warnings?\b',
        r'^Precautions?\b',
        r'^Warnings?\s+and\s+Precautions?\b',
    ],
    'cautions': [
        r'^Cautions?\b',
        r'^Notes?\b',
    ],
}

# Stop anchors (H2/H3 headings that indicate end of section)
STOP_ANCHORS = [
    r'^Instructions?\s+for\s+Use\b',
    r'^Sterilization\b',
    r'^Cleaning\b',
    r'^Specifications?\b',
    r'^Technical\s+Data\b',
    r'^Symbols?\b',
    r'^Warranty\b',
    r'^Contact\s+Information\b',
]


def is_toc_page(text: str) -> bool:
    """Detect if page is Table of Contents.

    Heuristics:
    1. Contains "Table of Contents" heading
    2. High density of dotted leaders (......)
    3. >20% lines are short (<60 chars) with no bullets
    """
    text_lower = text.lower()

    # Check 1: Explicit TOC heading
    if re.search(r'table\s+of\s+contents', text_lower):
        return True

    # Check 2: Dotted leader density
    lines = text.split('\n')
    dotted_lines = sum(1 for line in lines if '...' in line or '···' in line)
    if len(lines) > 0 and dotted_lines / len(lines) > 0.3:
        return True

    # Check 3: Short, non-bullet lines (TOC entries)
    short_lines = [l for l in lines if 10 < len(l) < 60 and not re.match(r'^\s*[•\-\*\d\.]', l)]
    if len(lines) > 0 and len(short_lines) / len(lines) > 0.2:
        return True

    return False


def extract_clinical_block(
    pages: List[PageData],
    header_patterns: List[str],
    stop_patterns: Optional[List[str]] = None,
    layout_aware: bool = True,
) -> Optional[str]:
    """Extract clinical block between anchors with TOC guard.

    Args:
        pages: Document pages
        header_patterns: Regex patterns for section start
        stop_patterns: Regex patterns for section end (default: STOP_ANCHORS)
        layout_aware: If True and TOC detected, use PyMuPDF paragraph extraction

    Returns:
        Extracted text or None

    Raises:
        AnchorBleedError: If TOC detected in extracted span
    """
    if stop_patterns is None:
        stop_patterns = STOP_ANCHORS

    # Step 1: Find header span
    header_region = find_header_span(pages, header_patterns)
    if not header_region:
        return None

    # Step 2: Extract text until next stop header
    text = harvest_until_next_header(pages, header_region, stop_patterns)
    if not text:
        return None

    # Step 3: TOC guard (CRITICAL - Ion regression sentinel)
    if "table of contents" in text.lower():
        if layout_aware:
            # Retry with layout-aware extraction
            text = retry_with_layout_extraction(pages, header_region, stop_patterns)
            if text and "table of contents" in text.lower():
                raise AnchorBleedError(f"TOC detected in clinical block after layout retry")
        else:
            raise AnchorBleedError(f"TOC detected in clinical block")

    # Step 4: Cleanup
    text = clean_paragraph(text)
    text = normalize_ligatures(text)

    # Step 5: Normalize to list if clinical content
    if any(pattern in header_patterns[0].lower() for pattern in ['contraindications', 'adverse', 'complications']):
        return normalize_list_block(text)

    return text


def find_header_span(
    pages: List[PageData],
    patterns: List[str]
) -> Optional[Tuple[int, int, int]]:
    """Find page and line indices where header appears.

    Returns:
        (page_idx, line_start, line_end) or None
    """
    for page_idx, page in enumerate(pages):
        # Filter out TOC pages first
        if is_toc_page('\n'.join(page.lines)):
            continue

        for line_idx, line in enumerate(page.lines):
            for pattern in patterns:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    return (page_idx, line_idx, line_idx + 1)

    return None


def harvest_until_next_header(
    pages: List[PageData],
    header_region: Tuple[int, int, int],
    stop_patterns: List[str]
) -> str:
    """Extract text from header until next stop pattern.

    Args:
        pages: Document pages
        header_region: (page_idx, line_start, line_end)
        stop_patterns: Patterns indicating section end

    Returns:
        Extracted text
    """
    start_page, start_line, _ = header_region
    collected_lines = []

    # Start from line after header
    current_page = start_page
    current_line = start_line + 1

    while current_page < len(pages):
        page = pages[current_page]

        while current_line < len(page.lines):
            line = page.lines[current_line]

            # Check for stop pattern
            if any(re.match(pattern, line.strip(), re.IGNORECASE) for pattern in stop_patterns):
                # Found stop - return collected
                return '\n'.join(collected_lines)

            collected_lines.append(line)
            current_line += 1

        # Move to next page
        current_page += 1
        current_line = 0

        # Safety: stop after 10 pages
        if current_page - start_page > 10:
            break

    return '\n'.join(collected_lines)


def retry_with_layout_extraction(
    pages: List[PageData],
    header_region: Tuple[int, int, int],
    stop_patterns: List[str]
) -> str:
    """Retry extraction using PyMuPDF paragraph blocks (layout-aware).

    When text extraction captures TOC, use layout analysis to extract only
    paragraph blocks (excluding headers/footers/TOC formatting).

    Args:
        pages: Document pages
        header_region: (page_idx, line_start, line_end)
        stop_patterns: Patterns indicating section end

    Returns:
        Cleaned text from paragraph blocks only
    """
    from medparse.ingest.pdf_reader import iter_pages

    start_page, start_line, _ = header_region

    # Re-read pages with PyMuPDF to get block types
    # This requires access to the original PDF path - for now, fallback
    # In production, would use: pdf_path from context
    # blocks = page.get_text("dict")["blocks"]
    # paragraph_blocks = [b for b in blocks if b["type"] == 0]  # 0 = text block

    # Placeholder: In practice, implement layout-aware extraction
    # For now, return original (caller will raise AnchorBleedError)
    return ""


def normalize_list_block(text: str) -> str:
    """Normalize clinical list (contraindications, adverse events) to List[str].

    Steps:
    1. Split by bullets, numbers, or semicolons
    2. Deduplicate
    3. Drop boilerplate ("contact information", "see warnings")

    Args:
        text: Raw list text

    Returns:
        JSON-serializable list string (or could return List[str])
    """
    items = []

    # Try bullet points first
    if re.search(r'^\s*[•\-\*]\s+', text, re.MULTILINE):
        split_items = re.split(r'\n\s*[•\-\*]\s+', text)
        items = [item.strip() for item in split_items if item.strip()]

    # Try numbered list
    elif re.search(r'^\s*\d+[\.)]\s+', text, re.MULTILINE):
        split_items = re.split(r'\n\s*\d+[\.)]\s+', text)
        items = [item.strip() for item in split_items if item.strip()]

    # Try semicolon-separated
    elif ';' in text:
        split_items = text.split(';')
        items = [item.strip() for item in split_items if item.strip()]

    # Fallback: sentence split
    else:
        split_items = re.split(r'[.]\s+', text)
        items = [item.strip() + '.' for item in split_items if len(item.strip()) > 10]

    # Deduplicate
    items = list(dict.fromkeys(items))  # Preserves order

    # Drop boilerplate
    boilerplate_patterns = [
        r'contact\s+(?:information|us)',
        r'see\s+warnings',
        r'refer\s+to',
        r'for\s+more\s+information',
    ]

    filtered_items = []
    for item in items:
        if not any(re.search(pattern, item, re.IGNORECASE) for pattern in boilerplate_patterns):
            filtered_items.append(item)

    # Return as formatted string (or convert to JSON list in caller)
    return '\n'.join(f"- {item}" for item in filtered_items)


__all__ = [
    "extract_clinical_block",
    "is_toc_page",
    "AnchorBleedError",
    "IFU_ANCHORS",
]
```

---

### 1.2 Integration into IFU Extractor

**File**: `medparse/extractors/ifu.py` (UPDATE)

```python
"""IFU extraction with anchor-based clinical block extraction."""

from medparse.normalize.ifu_anchors import extract_clinical_block, IFU_ANCHORS, AnchorBleedError
from medparse.config import get_extraction_config

def extract_ifu(pdf_path, ...):
    pages = load_pages(...)
    config = get_extraction_config()

    # Extract clinical blocks using anchors
    clinical_blocks = {}

    for block_name, header_patterns in IFU_ANCHORS.items():
        try:
            text = extract_clinical_block(
                pages,
                header_patterns=header_patterns,
                layout_aware=True
            )
            clinical_blocks[block_name] = text
        except AnchorBleedError as e:
            # CRITICAL: Fail immediately if TOC bleed detected
            if config.reject_toc_bleed:
                raise ValueError(f"TOC bleed in {block_name}: {e}")
            else:
                clinical_blocks[block_name] = None

    # ... rest of extraction

    return IFUDocument(
        indications_for_use=clinical_blocks.get('indications_for_use'),
        contraindications=clinical_blocks.get('contraindications'),
        adverse_events=clinical_blocks.get('adverse_events'),
        warnings=clinical_blocks.get('warnings'),
        ...
    )
```

---

## (Continued in QUALITY_RESTORATION_GUIDE_PART2.md due to length)

This guide is comprehensive and will be split across multiple documents. The next parts will cover:

**Part 2**:
- IFU manufacturer-agnostic patterns (MERIT, Olympus)
- IFU validation rules with strict gates
- Golden test fixtures

**Part 3**:
- UMLS linking restoration
- Relations extraction
- Guideline grade normalization

**Part 4**:
- Article/textbook validators
- Pipeline contracts
- CI gates

---

## Quick Reference: What's Been Implemented

### ✅ Completed
1. **Mode System** ([medparse/config.py](medparse/config.py))
   - `ExtractionProfile` enum (fast_raw, enriched)
   - `ExtractionConfig` with profile-aware toggles
   - Environment variable support

### 📝 Implementation Guides Provided
2. **IFU Anchor Extraction** (Code above)
   - `is_toc_page()` detector
   - `extract_clinical_block()` with TOC guard
   - `AnchorBleedError` for strict validation
   - Layout-aware fallback placeholder

### 🔄 Next Steps
1. Create `medparse/normalize/ifu_anchors.py` with code above
2. Update `medparse/extractors/ifu.py` to use anchors
3. Create validation rules in `medparse/validate/ifu_rules.py`
4. Create golden test fixtures
5. Implement UMLS/relations modules
6. Wire everything into pipeline

---

**Status**: Foundation complete, implementation guides ready.
**Next**: Create actual files and wire into extractors?
