# IFU Extraction Improvements Plan

## Latest fixes from external review (2025-09-09)
- Added paragraph-level repair to merge shattered decimals (e.g., `6. 0. 0 → 6.0.0`) and join split model IDs (`IF 1000 → IF1000`) so paragraph_store content is safe for RAG.
- Stripped noisy instruction-manual footers (`EU-ME 3 INSTRUCTION MANUAL i`, `ALT-Pro INSTRUCTION MANUAL 31`, `BW-18V INSTRUCTION MANUAL`) during cleanup to stop footer bleed into paragraphs and safety blocks.
- Suppressed table “ghosting” by dropping paragraph_store entries that duplicate structured tables on the same page; tables stay as the single source of truth.
- Tagged paragraph languages (English vs Japanese) to enable filtering or splitting mixed-language manuals.
- Emitting per-language JSON splits when mixed-language content is detected (e.g., BW-18V_en.json, BW-18V_ja.json) with chunks dropped to avoid cross-language bleed.
- Flagging complex tables (wide, fragmented headers, long tables) for vision-based extraction; config flag `emit.tables.vision_route=true` can force the hint.
- TODO next: upgrade complex table extraction (license/compatibility matrices) via a vision-backed parser.

## Issue Analysis Summary

### 1. Intuitive Ion (Critical Issues)
- **Wrong indications text**: Extracted "Intended Use" (page 12) instead of "Indications for Use" (page 11)
- **Wrong model**: Extracted "Project" instead of "IF 1000"
- **Wrong date**: Used copyright year (2019) instead of revision date (2024.08)

### 2. ERBE System Carrier (Structural Issues)
- **Failed ToC detection**: Didn't detect pages 3-6 "What would you like to do?" table of contents
- **Wrong date**: Used 2018 instead of 2025 copyright date

### 3. Olympus ALT-Pro (Minor Issues)
- **Wrong product_name**: Listed an accessory instead of main device (model field correct)

## Proposed Solutions

### 1. Fix Indications vs Intended Use Confusion

#### Problem
The current code has ambiguous logic for handling "Indications for Use" vs "Intended Use". For Intuitive Ion, it extracted the wrong section.

#### Solution
```python
# Update medparse/normalize/ifu_anchors.py

def _build_indications_validator(toc_mask: Set[int]) -> Callable[[Section], bool]:
    """Validate that the section is truly 'Indications for Use' not 'Intended Use'."""
    mask = {int(page) for page in toc_mask if isinstance(page, int)}

    def _validator(section: Section) -> bool:
        if section.start_page is None:
            return False
        if mask and section.start_page in mask:
            return False

        lines = section.lines or []
        if not lines:
            return False

        heading = lines[0].strip().lower()

        # Critical: Ensure we get "Indications for Use", not "Intended Use"
        # Check for exact heading match
        if "indications for use" in heading or "indications of use" in heading:
            return True

        # Reject if it's "Intended Use" (different field)
        if "intended use" in heading and "indications" not in heading:
            return False

        # Check if numbered section with "indications"
        if INDICATION_HEADING_RE.search(lines[0]):
            body_lines = [line for line in lines[1:] if line.strip() and not is_toc_like_para(line)]
            return len(body_lines) >= 2

        return False

    return _validator
```

#### Configuration Update
```yaml
# Update configs/run_ifu.yaml
ifu:
  anchors:
    indications_for_use:
      start:
        - "indications for use"
        - "indications of use"  # Alternate form
      stops:
        - "contraindications"
        - "warnings"
        - "precautions"
      # Remove "intended use" from stops - it's a different field!

    intended_use:
      start:
        - "intended use"
        - "intended purpose"
      stops:
        - "intended user"
        - "indications for use"  # Stop at indications section
        - "contraindications"
        - "warnings"
```

### 2. Improve ToC Detection for ERBE

#### Problem
Failed to detect "What would you like to do?" style ToC in ERBE document.

#### Solution
```python
# Update medparse/ifu/toc_guard.py

TOC_KEYWORDS = (
    "table of contents",
    "contents",
    "index",
    "indice",
    "indice.",
    "summary of sections",
    "what would you like to do",  # Add ERBE-specific pattern
    "quick reference",
    "overview",
)

def _looks_like_toc_page(page: PageData, config: TocGuardConfig) -> bool:
    """Enhanced ToC detection with question-style patterns."""
    if not page.lines:
        return False

    lines = [line.strip() for line in page.lines if line.strip()]
    if not lines:
        return False

    lowered_lines = [line.lower() for line in lines]

    # Check for ToC keywords
    for keyword in TOC_KEYWORDS:
        if any(keyword in line for line in lowered_lines):
            return True

    # New: Check for question-based ToC (ERBE style)
    # "What would you like to do?" followed by action items
    question_patterns = [
        r"what\s+(would\s+you\s+like|do\s+you\s+want)\s+to",
        r"how\s+to\s+use\s+this",
        r"quick\s+start\s+guide",
    ]

    for pattern in question_patterns:
        if any(re.search(pattern, line, re.IGNORECASE) for line in lines):
            # Check if followed by action items or page numbers
            numbered_lines = sum(1 for line in lines if PAGE_NUMBER_RE.search(line))
            if numbered_lines >= 2 or len(lines) >= 5:
                return True

    # Existing dot leader and page number logic...
    dotted_lines = sum(1 for line in lines if DOT_LEADER_RE.search(line))
    numbered_lines = sum(1 for line in lines if PAGE_NUMBER_RE.search(line))

    # ... rest of existing logic ...
```

#### ERBE-Specific Configuration
```yaml
# Update configs/run_ifu.yaml
ifu:
  manufacturer_overrides:
    "ERBE":
      toc_guard:
        density_threshold: 0.55  # Lower threshold for ERBE
        keywords_extra:
          - "what would you like to do"
          - "quick reference"
          - "where to find"
        require_strict_toc: false
    "ERBE ELEKTROMEDIZIN GMBH":
      # Same settings as ERBE
```

### 3. Fix Metadata Extraction

#### A. Fix Intuitive Model Detection
```python
# Update medparse/manufacturers/intuitive.py

def _create_profile():
    """Enhanced Intuitive profile with better model detection."""
    from medparse.manufacturers import ManufacturerProfile

    return ManufacturerProfile(
        name="Intuitive Surgical",
        name_patterns=[
            r"\bIntuitive\s+Surgical",
            r"\bIntuitive\s+Surgical,?\s+Inc",
            r"\bIon\s+Endoluminal\s+System",  # Product-specific
        ],
        pn_patterns=[
            r'\b(5\d{5}-\d{2})\b',  # 553990-11 format
        ],
        rev_patterns=[
            r'\bRev(?:ision)?\s*\.?\s*([A-Z]\d?)\b',  # Rev C, Rev. C, Revision C
        ],
        date_patterns=[
            # Prioritize revision date patterns
            r'\b\d{4}\s*\.\s*\d{2}\b',  # 2024. 08 (revision date format)
            r'\b\d{4}\s*[.\-]\s*\d{2}\b',  # 2024-08, 2024.08
            # Month Year as fallback
            r'\b(Jan(?:uary)?|Feb(?:ruary)?|...|Dec(?:ember)?)\s+\d{4}\b',
        ],
        model_patterns=[
            # More specific patterns
            r'\bModel\s*:\s*([A-Z]{1,3}\s?\d{3,4})\b',  # Model: IF 1000
            r'\bModel\s+No\.\s*([A-Z]{1,3}\s?\d{3,4})\b',  # Model No. IF 1000
            r'\b([A-Z]{1,3}\s?\d{3,4})(?=\s+Model|\s+System)',  # IF 1000 Model
            # Exclude false positives
            r'(?<!Project\s)\b([A-Z]{1,3}\s?\d{3,4})\b',  # Not "Project IF1000"
        ],
        normalize=normalize_intuitive_front_matter,
    )
```

#### B. Fix ERBE Date Detection
```python
# Update medparse/manufacturers/erbe.py

def _create_profile():
    """Enhanced ERBE profile with copyright date detection."""
    from medparse.manufacturers import ManufacturerProfile

    return ManufacturerProfile(
        name="ERBE",
        name_patterns=[
            r"\bERBE\b",
            r"ERBE\s+Elektromedizin",
        ],
        pn_patterns=[
            r'\b(\d{5}-\d{3})\b',  # 30180-103, 85100-172
            r'Art\.?\s*-?\s*Nr\.?\s*[:#]?\s*(\d{5}-\d{3})',  # Art.-Nr. 20180-110
        ],
        rev_patterns=[
            r'\b(?:Rev\.?\s*)?([A-Z0-9]+\d{5,6})\b',  # D294849 (revision code)
            r'\b(V\s*\d{3,6})\b',  # V 25709
        ],
        date_patterns=[
            # Prioritize copyright symbol dates (most recent)
            r'©\s*(\d{4})',  # © 2025
            r'Copyright\s+(\d{4})',  # Copyright 2025
            # Then revision dates
            r'\b(\d{4})-(\d{2})\b',  # 2025-01
            r'\b(\d{2})\.(\d{2})\.(\d{4})\b',  # 31.12.2024
        ],
        model_patterns=[
            r'\b(System\s+Carrier(?:\s+Performance)?)\b',  # System Carrier Performance
            r'\b(AUTOCON)\s*(?:II|III|[0-9]+)?\b',
            r'\b(VIO)\s*(?:[0-9]+)?\b',
            r'\b(APC)\s*(?:[0-9]+)?\b',
        ],
        normalize=normalize_erbe_front_matter,
    )
```

#### C. Fix Olympus Product Name
```python
# Update medparse/manufacturers/olympus.py (create if doesn't exist)

def normalize_olympus_front_matter(data: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """Normalize Olympus front-matter with product name validation."""
    normalized = data.copy()

    # Validate product_name isn't an accessory
    if normalized.get("product_name"):
        product = normalized["product_name"]
        # Check for accessory keywords
        accessory_keywords = [
            "leak test", "tube", "accessory", "adapter",
            "connector", "cable", "replacement"
        ]
        if any(keyword in product.lower() for keyword in accessory_keywords):
            # Try to use model as product_name if available
            if normalized.get("model"):
                normalized["product_name"] = normalized["model"]
            else:
                # Clear it - better to have None than wrong value
                normalized["product_name"] = None

    # Use model as fallback for product_name
    if not normalized.get("product_name") and normalized.get("model"):
        normalized["product_name"] = normalized["model"]

    return normalized
```

### 4. Enhanced Second-Pass Validation

#### Create new patcher for cross-field validation
```python
# New file: medparse/second_pass/patchers/ifu_metadata_validator.py

"""Validate and fix metadata extraction issues."""

from typing import Dict, Optional
import re
from datetime import datetime

from medparse.schema.ifu import IFUDocument
from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_metadata_validator"

def validate_and_fix_metadata(document: IFUDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    """Validate and fix common metadata extraction errors."""
    modifications = {}

    # 1. Validate publication_date isn't just a copyright year
    if document.publication_date:
        # Check if it's just a year (suspicious)
        if re.match(r'^\d{4}$', document.publication_date):
            # Search for a more specific date in the first 3 pages
            for entry in ctx.paragraph_store.values():
                page_no = entry.get("page", 999)
                if page_no > 3:
                    continue
                text = entry.get("text", "")
                # Look for revision dates
                revision_match = re.search(
                    r'(?:Revision|Rev\.?|Version)\s*:?\s*(\d{4}[\s.]\d{2})',
                    text
                )
                if revision_match:
                    new_date = revision_match.group(1).replace(' ', '-').replace('.', '-')
                    document.publication_date = new_date + "-01"
                    modifications["publication_date_fixed"] = 1
                    break

    # 2. Validate model isn't "Project" or similar non-model text
    if document.model:
        invalid_models = ["Project", "Draft", "Template", "Document"]
        if document.model in invalid_models:
            # Try to find real model number
            for entry in ctx.paragraph_store.values():
                page_no = entry.get("page", 999)
                if page_no > 5:
                    continue
                text = entry.get("text", "")
                model_match = re.search(r'\bModel\s*:?\s*([A-Z]{1,3}\s?\d{3,4})', text)
                if model_match:
                    document.model = model_match.group(1)
                    modifications["model_fixed"] = 1
                    break

    # 3. Ensure indications_for_use is not intended_use
    if document.indications_for_use and document.intended_use:
        # If they're the same, we likely have duplication
        if document.indications_for_use == document.intended_use:
            # Search for the real indications section
            for entry in ctx.paragraph_store.values():
                text = entry.get("text", "")
                if "indications for use" in text.lower():
                    # Extract the content after the heading
                    lines = text.split('\n')
                    for i, line in enumerate(lines):
                        if "indications for use" in line.lower():
                            content = '\n'.join(lines[i+1:]).strip()
                            if content and content != document.intended_use:
                                document.indications_for_use = content
                                modifications["indications_fixed"] = 1
                                break

    if modifications:
        return SecondPassPatchResult(
            name=PATCH_NAME,
            applied=True,
            modifications=modifications,
            reasons=list(modifications.keys()),
        )

    return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_issues_found")
```

### 5. Testing Framework

#### Create test suite for IFU extraction
```python
# New file: tests/test_ifu_extraction.py

"""Test suite for IFU extraction improvements."""

import pytest
from pathlib import Path
from medparse.cli import extract_ifu

# Test cases based on the three problematic IFUs
TEST_IFUS = {
    "intuitive_ion": {
        "file": "ifu_ion-endoluminal-system.pdf",
        "expected": {
            "indications_for_use": "should contain 'diagnostic and therapeutic procedures'",
            "model": "IF1000",  # Not "Project"
            "publication_date": "2024-08-01",  # Not "2019"
        }
    },
    "erbe_system_carrier": {
        "file": "ifu_30180-103-erbe-en-systemcarrier.pdf",
        "expected": {
            "toc_pages_dropped": [3, 4, 5, 6],  # Should detect ToC
            "publication_date": "2025-01-01",  # Not "2018"
        }
    },
    "olympus_alt_pro": {
        "file": "ifu_alt-pro-instruction-manual.pdf",
        "expected": {
            "product_name": "ALT PRO",  # Not the leak test accessory
            "model": "ALT PRO",
        }
    }
}

@pytest.mark.parametrize("test_name,test_data", TEST_IFUS.items())
def test_ifu_extraction(test_name, test_data):
    """Test IFU extraction for known problematic documents."""
    result = extract_ifu(test_data["file"])

    for field, expected_value in test_data["expected"].items():
        if field == "toc_pages_dropped":
            assert result["_toc_info"]["pages_dropped"] == expected_value
        elif "should contain" in str(expected_value):
            keyword = expected_value.replace("should contain ", "").strip("'")
            assert keyword in result[field].lower()
        else:
            assert result[field] == expected_value
```

## Implementation Priority

1. **HIGH**: Fix Indications vs Intended Use (affects clinical accuracy)
2. **HIGH**: Fix metadata extraction (dates, models)
3. **MEDIUM**: Improve ToC detection for ERBE-style documents
4. **LOW**: Fix Olympus product name extraction

## Testing Strategy

1. Run extraction on the three problematic IFUs
2. Verify all issues are fixed
3. Run on full IFU dataset to ensure no regressions
4. Create golden test set with expected outputs

## Rollback Plan

Keep original configuration as `configs/run_ifu_v1.yaml` before making changes.

## Success Metrics

- Intuitive Ion: Correct indications, model="IF1000", date="2024-08"
- ERBE: ToC pages 3-6 dropped, date="2025"
- Olympus: product_name="ALT PRO" not accessory name
- No regression on other IFUs in the dataset
