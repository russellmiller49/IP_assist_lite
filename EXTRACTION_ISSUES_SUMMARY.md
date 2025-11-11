# MEDPARSE EXTRACTION: CRITICAL ISSUES & KEY FINDINGS

**Date**: 2025-11-11
**Status**: Extraction pipeline thoroughly analyzed

---

## QUICK REFERENCE: ABSOLUTE FILE PATHS & LINE NUMBERS

### IFU EXTRACTION PIPELINE
| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| **Main Extractor** | `/home/user/IP_assist_lite/medparse/extractors/ifu.py` | 94-386 | Core IFU extraction orchestration |
| **Front-Matter** | `/home/user/IP_assist_lite/medparse/ifu/frontmatter.py` | 284-403 | Extract metadata (manufacturer, product_name, revision) |
| **Clinical Fields** | `/home/user/IP_assist_lite/medparse/normalize/ifu_anchors.py` | 61-243 | Lift indications_for_use, contraindications, adverse_events |
| **Anchor Slicing** | `/home/user/IP_assist_lite/medparse/ifu/anchors.py` | 504-711 | Core section boundary detection |
| **TOC Detection** | `/home/user/IP_assist_lite/medparse/ifu/toc_guard.py` | 95-276 | Detect and filter Table of Contents pages |
| **Manufacturer Maps** | `/home/user/IP_assist_lite/medparse/ifu/anchors.py` | 279-434 | Intuitive/Olympus-specific anchors |

### ARTICLE EXTRACTION & TABLES
| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| **Main Extractor** | `/home/user/IP_assist_lite/medparse/extractors/article.py` | 200+ | Article orchestration |
| **Table Ingestion** | `/home/user/IP_assist_lite/medparse/ingest/tables.py` | 28-113 | Extract tables from PDF |
| **Table Normalization** | `/home/user/IP_assist_lite/medparse/normalize/tables.py` | 1-137 | Merge continued tables, deduplicate |
| **Table Classification** | `/home/user/IP_assist_lite/medparse/normalize/tables_classifier.py` | 67-160+ | Gate false positives (3-gate validation) |
| **Table Mapping** | `/home/user/IP_assist_lite/medparse/extractors/article.py` | 823-835 | Convert TableBlock → EnhancedTable |
| **EnhancedTable Schema** | `/home/user/IP_assist_lite/medparse/schema/article.py` | 211-223 | Table schema definition |

### CONFIGURATION
| Config | File | Purpose |
|--------|------|---------|
| **IFU Config** | `/home/user/IP_assist_lite/configs/run_ifu.yaml` | Engine selection, TOC guard thresholds, manufacturer overrides |
| **Article Config** | `/home/user/IP_assist_lite/configs/run_article.yaml` | Zotero enrichment, table type filtering |

---

## IFU EXTRACTION: CRITICAL ISSUES

### 1. FRONT-MATTER EXTRACTION ISSUES

**Problem**: Metadata extraction relies on hardcoded patterns for only 3 manufacturers

**Location**: `/home/user/IP_assist_lite/medparse/ifu/frontmatter.py:17-40`

**Hardcoded Patterns**:
```python
MANUFACTURER_PATTERNS = [
    ("ERBE Elektromedizin GmbH", [regex patterns]),
    ("Intuitive Surgical, Inc.", [regex patterns]),
    ("Olympus Corporation", [regex patterns]),
]
```

**Failure Mode**: 
- Unknown manufacturers fall back to footer inference (line 326)
- Product name selection has 4 fallback sources (lines 375-565) but may not cover edge cases
- Filename extraction is last resort (lines 384-401)

**Key Functions**:
- `extract_front_matter()`: lines 284-403
- `_detect_manufacturer()`: lines 412-419
- `_select_product_name()`: lines 497-566
- `_normalize_date()`: lines 437-485

---

### 2. TOC DETECTION & ANCHOR BLEED

**Problem**: TOC guard uses 5 independent heuristics, but can still miss edge cases

**Location**: `/home/user/IP_assist_lite/medparse/ifu/toc_guard.py:156-194`

**Detection Rules** (must trigger at least 1):
1. **Explicit Keywords**: "table of contents", "contents", "index"
2. **Dotted Lines**: ≥2 dotted lines AND ≥2 page numbers
3. **Density Check**: dotted_ratio ≥ 0.20 AND numbered_ratio ≥ 0.40
4. **Short Lines**: ≥4 lines with 50% numbered, 70% short
5. **Numbered Headings**: ≥5 lines with ≥4 section-like headings

**Anchor Bleed Trimming** (lines 136-153):
```python
def trim_anchor_bleed(text, max_blocks=3, ratio_threshold=0.8):
    # Remove leading TOC in 6-line blocks where 80%+ lines are TOC-like
```

**Critical Validation** (lines 663-671):
```python
if field_name == "indications_for_use":
    if not _contains_indication_phrase(trimmed_text):
        break  # MUST contain "indicated for", "intended for", etc.
```

**Failure Mode**:
- If first section has no indication phrase, entire section rejected
- TOC bleed ratio threshold (0.8) may be too high
- Window limiting (3 pages) might not be enough for dense index pages

---

### 3. CLINICAL FIELD ANCHOR MAPPING

**Location**: `/home/user/IP_assist_lite/medparse/ifu/anchors.py:279-434`

**Fields Extracted**:
- indications_for_use
- intended_use
- intended_user
- intended_patient_population
- contraindications
- clinical_risks_and_benefits
- adverse_events

**Manufacturer-Specific Anchors**:

**Intuitive Surgical** (lines 279-374):
- Uses section-numbered anchors (1.4.1, 1.4.2)
- Has stop anchor "table 1.1" to prevent table content
- min_anchor_page: 10 (Ion manuals structure)

**Olympus** (lines 377-426):
- Uses plain text anchors
- Recognizes "important information" block
- Shorter, 2-4 page leaflets

**Problem**: No fallback for unlisted manufacturers - uses DEFAULT_SECTION_ANCHORS only

---

### 4. SECTION SLICING ALGORITHM COMPLEXITY

**Location**: `/home/user/IP_assist_lite/medparse/ifu/anchors.py:504-711`

**Multi-Level Validation Loop**:
1. TOC page filtering (lines 520-538)
2. Minimum page enforcement (lines 552-574)
3. Anchor pattern matching (lines 587-597)
4. Heading validation (lines 617-620)
5. Section extraction (lines 636-641)
6. Text cleaning (lines 646-653)
7. TOC bleed trimming (lines 654)
8. Post-extraction validation (lines 659-666)
9. Window limiting if TOC detected (lines 667-673)
10. Section validator callback (lines 688-691)

**Potential Failure Points**:
- Multiple retry loops (max_attempts = len(pages))
- Expensive PDF operations repeated per anchor
- Complex interaction between validators

**Key Helper Functions**:
- `_contains_indication_phrase()` (1003-1011): Must find keywords or 2+ sentence marks
- `anchor_post_guard()` (846-861): First 10 lines must be <40% TOC-like
- `trim_anchor_bleed()` (136-153): Drops max 3 blocks of 6 lines each

---

## ARTICLE EXTRACTION: TABLE FORMATTING ISSUES

### 1. TABLE INGESTION LIMITATIONS

**Location**: `/home/user/IP_assist_lite/medparse/ingest/tables.py:28-113`

**Keyword Gate** (lines 31-33):
```python
TABLE_KEYWORDS = ("table", "status indicator", "led", "power button",
                  "complication", "sensitivity", "specificity", "adverse event")
```

**Problem**: 
- Medical articles have tables without keywords
- Falls back to inline extraction (pipe-delimited) if PDFPlumber fails
- No handling for multi-line headers

**Cell Normalization** (lines 55-65):
- Empty cells → ""
- Missing headers → auto-generate "col_1", "col_2"

---

### 2. TABLE CLASSIFICATION (3-GATE VALIDATION)

**Location**: `/home/user/IP_assist_lite/medparse/normalize/tables_classifier.py:67-160`

**Gate 1: Medical Headers** (line 86)
```python
MEDICAL_GLOSSARY = ['n', '%', 'p-value', 'ci', 'sensitivity', 'specificity', ...]
medical_headers = count_medical_headers(table_data.headers)
if medical_headers < 2:
    continue  # REJECT
```

**Gate 2: Paragraph Check** (line 91)
```python
if is_paragraph_table(table_data):
    continue  # REJECT (abstract mis-classified as table)
```

**Gate 3: Size Check** (lines 94-96)
```python
if len(headers) < 2 or len(rows) < 1:
    continue  # REJECT
```

**Gate 4: Cell Size** (line 98)
```python
if cell_exceeds_character_limit(table_data):
    continue  # REJECT
```

**Table Type Classification** (lines 30-55):
- diagnostic_accuracy
- baseline_characteristics
- complications
- outcomes
- diagnostic_yield
- reasons_for_failure

---

### 3. ARTICLE TABLE SCHEMA GAP: MARKDOWN FORMAT

**Location**: `/home/user/IP_assist_lite/medparse/schema/article.py:211-223`

**EnhancedTable Definition**:
```python
class EnhancedTable(MedparseModel):
    id: str
    label: Optional[str]
    caption: Optional[str]
    headers: List[List[str]]  # ← Supports multi-row headers
    stub_column: Optional[int]  # ← Not populated
    rows: List[List[str]]
    footnotes: List[TableFootnote]  # ← Not extracted
    table_type: Optional[str]
    truncated_cells: bool
```

**Mapping Implementation** (lines 823-835):
```python
def _map_tables(blocks):
    for idx, block in enumerate(blocks, start=1):
        tables.append(EnhancedTable(
            id=f"table_{idx}",
            caption=block.caption,
            headers=[block.headers],  # ← Wraps single row in list
            rows=block.rows,
            page=block.page,
            table_type=block.table_type,
        ))
```

**Critical Gaps**:
1. **No markdown rendering** - Tables output as JSON arrays only
2. **No column alignment tracking** - No width, alignment, or type info
3. **No multi-row header stitching** - Schema supports but extraction doesn't populate
4. **No stub column detection** - Always None
5. **No footnote extraction** - Always empty list
6. **No cell wrapping** - Long cells truncated with no formatting

---

## CONFIGURATION CRITICAL POINTS

### IFU Configuration (run_ifu.yaml, lines 36-99)

**Engine Selection**:
```yaml
engine:
  text: pymupdf                    # Primary for text
  tables: pdfplumber               # Separate engine for tables
  auto:
    sample_pages: 6                # Check first 6 pages
    char_density_threshold: 1400
    image_density_threshold: 0.6
```

**TOC Guard**:
```yaml
toc_guard:
  enabled: true
  density_threshold: 0.65          # Ratio of TOC markers
  dot_leader_min: 0.20             # Min dotted lines ratio
  page_number_ratio: 0.40          # Min page numbers ratio
```

**Manufacturer Overrides**:
```yaml
"INTUITIVE SURGICAL, INC.":
  min_anchor_page: 10              # Don't search before page 10
  toc_guard:
    density_threshold: 0.55        # More aggressive
    dot_leader_min: 0.15
```

---

## EXTRACTION PIPELINE FLOW

### IFU Pipeline
```
PDF → load_pages(engine) → repair_space_poor_pages() → detect_manufacturer()
  → extract_front_matter() → strip_furniture() → collect_lines()
  → iter_section_windows() (structural section extraction)
  → lift_ifu_clinical_fields() [CRITICAL BOTTLENECK]
    → resolve_toc_guard() → apply_toc_guard()
    → resolve_anchor_map() (merge manufacturer-specific)
    → For each field: slice_section()
      → strip_toc() → _find_first_anchor_line()
      → slice_between() → clean_paragraph()
      → _truncate_to_stop() → normalize_bullets()
      → trim_anchor_bleed() → anchor_post_guard()
      → [special validations per field]
  → parse_contraindications() / sanitize_adverse_events()
  → collect_tables() → clean_tables() [IFU-specific allowlist]
  → build_safety_blocks() → normalize_references()
  → IFUDocument.model_validate()
```

### Article Table Pipeline
```
PDF → load_pages() → collect_tables() → classify_and_gate_tables()
  → [Gate 1: medical_headers >= 2]
  → [Gate 2: not paragraph_table]
  → [Gate 3: size check]
  → [Gate 4: cell size check]
  → classify_table_type() → _map_tables()
  → EnhancedTable objects (wrapped in ArticleDocument.tables)
```

---

## RECOMMENDATIONS FOR FIXING CRITICAL ISSUES

### IFU Issues Priority

**HIGH (Blocking)**:
1. **Indication phrase validation** too strict - add heuristic fallbacks
2. **Manufacturer anchor maps** incomplete - add generic fallback strategies
3. **TOC bleed threshold** (0.8) may need tuning per manufacturer

**MEDIUM (Affecting Quality)**:
1. **Front-matter patterns** need expansion for new manufacturers
2. **Anchor retry loop** performance - implement smarter pruning
3. **Window limiting** (3 pages) may be insufficient for some layouts

**LOW (Polish)**:
1. Extract software versions more robustly
2. Implement small_leaflet_policy fully
3. Add section span tracking for debugging

### Article Table Issues Priority

**CRITICAL (Breaking)**:
1. **No markdown output format** - implement table-to-markdown converter
2. **No column alignment preservation** - add column metadata tracking
3. **No multi-row header support** - populate headers properly

**HIGH (Quality)**:
1. **No stub column detection** - implement smart stub column finder
2. **No footnote extraction** - add footnote parsing
3. **No cell wrapping** - implement cell truncation with ellipsis

**MEDIUM (Robustness)**:
1. Table type classification confidence scoring
2. Fallback for tables without medical headers
3. Column type inference (numeric vs text)

---

## KEY PERFORMANCE CHARACTERISTICS

### Time Complexity
- **IFU extraction**: O(n_pages × n_anchors × n_validation_passes)
- **Anchor retry**: Up to n_pages attempts per field
- **TOC guard**: O(n_pages) scan, limited to first 15 pages

### Space Complexity
- Page cache: O(n_pages × avg_page_size)
- Anchor patterns: O(n_fields × avg_anchors_per_field)
- Dedup table map: O(unique_table_titles)

### Failure Modes
- **Timeout**: pymupdf (70s), pdfplumber (85s) per document
- **Memory**: Large PDFs (>200 pages) with pdfplumber
- **False negatives**: Missing anchors due to layout variations
- **False positives**: TOC pages misclassified as content

---

## DEBUG TIPS

### IFU Extraction Debugging
1. Check `pipeline_info.toc_guard_applied` - was TOC guard used?
2. Check `pipeline_info.anchor_bleed_errors` - which fields failed?
3. Check `_anchor_spans` in output - start/end page per field
4. Check `pipeline_info.manufacturer_detection` - was manufacturer detected?

### Article Table Debugging
1. Check table_type field - was classification correct?
2. Check truncated_cells flag - were cells too long?
3. Check headers List[List[str]] structure - is multi-row properly nested?
4. Cross-ref with page number for visual inspection

---

**See MEDPARSE_EXTRACTION_ANALYSIS.md for complete code listings and line-by-line implementation details.**

