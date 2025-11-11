# MEDPARSE EXTRACTION LOGIC - COMPREHENSIVE ANALYSIS

**Date**: 2025-11-11
**Scope**: IFU Extraction, Article Table Formatting, Anchor/ToC Detection, Front-matter Extraction

---

## PART 1: ENTRY POINTS & CLI ORCHESTRATION

### CLI Entry Points
**File**: `/home/user/IP_assist_lite/medparse/cli.py`

#### extract-ifus Command
- **Lines 226-318**: Main IFU CLI handler
- `ifu_engine_override`: Override IFU extraction engine (hybrid|pdfplumber|pymupdf)
- `ifu_fast_long_docs`: Enable two-pass fast-path for long IFUs (pages > threshold)
- `second_pass`: auto|off|always - Second-pass remediation stage

#### extract-articles Command  
- **Lines 58-142**: Article CLI handler
- `tables_mode`: compact|verbatim for table emit
- `evidence_policy`: compact|verbatim for evidence handling
- Key difference: Articles support Zotero enrichment, IFUs do not

### Configuration Loading
- **Lines 470-478**: Config override resolution
- Combines user CLI flags with YAML config (run_ifu.yaml or run_article.yaml)
- Profile override: enriched|fast_raw

---

## PART 2: IFU EXTRACTION PIPELINE

### 2.1 Main IFU Extractor
**File**: `/home/user/IP_assist_lite/medparse/extractors/ifu.py`
**Lines**: 94-386

#### Key Function: `extract_ifu()`

**Input**:
- `pdf_path`: Path to PDF
- `engine`: pymupdf|pdfplumber|hybrid
- `page_limit`: Optional max pages
- `pages`: Optional pre-loaded PageData
- `config`: ExtractionConfig object

**Processing Steps** (lines 104-385):

1. **Page Loading & Repair** (lines 107-122)
   ```python
   pages = load_pages(pdf_path, engine=engine, max_pages=page_limit)
   pages, spacing_info = repair_space_poor_pages(...)  # Fix text spacing
   ```
   - Calls `engine_select.repair_space_poor_pages()` to fix character spacing issues
   - Returns `spacing_info` with metrics (space_ratio_before/after, avg_token_length)

2. **Front-Matter Extraction** (lines 125-137)
   ```python
   manufacturer_hint = detect_manufacturer(pages)  # From IFU manufacturers
   meta = extract_front_matter(
       pages,
       metadata_title=pdf_path.stem,
       manufacturer_hint=manufacturer_hint,
       manufacturer_source=manufacturer_source,
   )
   ```
   - Extracts: `manufacturer`, `product_name`, `part_number`, `revision`, `publication_date`, `model`
   - Returns dict with `_provenance` showing extraction source

3. **Page Furniture Stripping** (lines 140-146)
   ```python
   clean_lines_by_page = strip_furniture(lines_by_page, threshold=0.6)
   # Update pages with cleaned lines
   ```

4. **Section Extraction** (lines 152-155)
   ```python
   for heading, next_heading in iter_section_windows(pages):
       text, _evidence, _ = section_text_between(pages, heading, next_heading)
       section_text[heading.title.lower()] = text
   ```

5. **Clinical Field Lifting** (lines 215-222)
   ```python
   toc_guard_info = lift_ifu_clinical_fields(
       pages, doc_kwargs,
       settings=ifu_settings,
       manufacturer=meta.get("manufacturer")
   )
   ```
   - **CRITICAL**: Populates contraindications, adverse_events, indications_for_use, etc.
   - Returns toc_guard_info with applied pages, heuristics

6. **Safety Block Extraction** (line 163)
   ```python
   safety_blocks = build_safety_blocks(pages, manufacturer=manufacturer_for_safety)
   ```

7. **Table Collection** (line 183)
   ```python
   "tables": collect_tables(tables_pages),
   ```

8. **Document Assembly** (lines 171-286)
   - Builds IFUDocument.model_validate(doc_kwargs)
   - Applies text cleanup: clean_paragraph() for narrative fields
   - Lists cleaned with clean_paragraph() for contraindications/adverse_events

---

### 2.2 Front-Matter Extraction
**File**: `/home/user/IP_assist_lite/medparse/ifu/frontmatter.py`
**Lines**: 284-403

#### Key Function: `extract_front_matter()`

**Input**:
- `pages`: Sequence of PageData
- `metadata_title`: From filename
- `manufacturer_hint`: Pre-detected from detect_manufacturer()
- `manufacturer_source`: Source of hint

**Processing** (lines 290-402):

1. **Coverage**:
   - Cover pages: first 3 pages
   - Tail pages: last 3 pages

2. **Metadata Fields**:
   ```python
   IDENTIFIER_PATTERNS = {
       "part_number": [regex patterns for PN, P/N, REF, etc.],
       "revision": [Rev, Version patterns],
       "publication_date": [date patterns - YYYY-MM-DD, YYYY-MM, Month YYYY],
       "model": [Model, Type, Series patterns],
   }
   ```

3. **Manufacturer Detection** (lines 304-313)
   - Hard-coded patterns for ERBE, Intuitive Surgical, Olympus
   - Fallback to footer inference via `infer_manufacturer_from_footer()`

4. **Product Name Selection** (lines 375-379)
   - Calls `_select_product_name()` with config patterns
   - Sources: pattern match > cover line scoring > model hint > metadata_title

5. **Date Normalization** (lines 346-352)
   ```python
   _normalize_date(raw_value) → "YYYY-MM-DD" or "YYYY-MM"
   publication_date_precision = "month" if YYYY-MM format
   ```

6. **Filename Extraction Fallback** (lines 384-401)
   - Regex: `D[0-9]{5,}` for document IDs
   - Regex: `[A-Z0-9]{2,}[-_][A-Z0-9]{2,}` for part numbers
   - Regex: `rev[_\-\s]*([A-Z0-9\.\-]{1,10})` for revisions

**FrontMatterResult Fields**:
- `manufacturer`, `product_name`, `product_name_source`
- `part_number`, `revision`, `publication_date`, `publication_date_precision`
- `model`, `print_code`
- `_provenance`: Dict[field_name] → source_name

---

### 2.3 IFU Clinical Field Lifting (Anchor Extraction)
**File**: `/home/user/IP_assist_lite/medparse/normalize/ifu_anchors.py`
**Lines**: 61-243

#### Key Function: `lift_ifu_clinical_fields()`

**Input**:
- `pages`: Sequence of PageData
- `ifu_json`: dict to populate with extracted fields
- `settings`: Dict with toc_guard, anchors, small_ifu_threshold
- `manufacturer`: For manufacturer-specific rules

**Processing** (lines 68-243):

1. **TOC Guard Setup** (lines 69-70)
   ```python
   guard = resolve_toc_guard(settings, manufacturer)
   filtered_pages, guard_report = strip_toc(pages, guard)
   ```

2. **Anchor Map Resolution** (lines 72-73)
   ```python
   anchors = resolve_anchor_map(anchor_overrides, manufacturer=manufacturer)
   ```
   - Merges DEFAULT_SECTION_ANCHORS with manufacturer-specific (INTUITIVE_ANCHORS, OLYMPUS_ANCHORS)
   - Also loads aliases from `configs/_shared/ifu_section_aliases.yaml`

3. **Clinical Fields Extraction** (lines 130-243)
   ```python
   for field, config in anchors.items():  # indications_for_use, contraindications, etc.
       start = config.get("start", [])
       stops = config.get("stops", [])
       
       section = slice_section(
           filtered_pages, start, stops,
           toc_guard=False,
           guard_config=guard,
           min_start_page=manufacturer_rules.get("min_anchor_page"),
           field_name=field,
           manufacturer_rules=manufacturer_rules,
           toc_mask=toc_mask_values,
       )
   ```

4. **Contraindications Parsing** (lines 187-192)
   ```python
   if field == "contraindications":
       parsed = parse_contraindications(block)
       if parsed:
           ifu_json[field] = parsed
   ```

5. **Clinical Risks Handling** (lines 195-204)
   ```python
   if field == "clinical_risks_and_benefits":
       risks = sanitize_adverse_events(block)
       # Merge into adverse_events or create new
   ```

6. **Error Tracking** (lines 162-166)
   ```python
   except AnchorBleedError as exc:
       errors.append(str(exc))
       error_fields.append(field)
       continue
   ```

**Return Value**:
- Dict with:
  - `enabled`: bool
  - `pages_dropped`: List[int] (TOC pages)
  - `anchors_bleed`: Dict[field] → trimmed_prefix (TOC lines removed)
  - `section_spans`: Dict[field] → {start_page, end_page}
  - Manufacturer-specific rules applied

---

### 2.4 Anchor/Section Slicing Logic
**File**: `/home/user/IP_assist_lite/medparse/ifu/anchors.py`
**Lines**: 504-711

#### Key Function: `slice_section()`

**Parameters**:
- `pages`: Sequence[PageData]
- `start_anchor`: Sequence[str] - anchors to START section (e.g., "indications for use")
- `stop_anchors`: Sequence[str] - anchors to STOP before (e.g., "intended use")
- `toc_guard`: bool - apply TOC filtering first
- `guard_config`: TocGuardConfig - parameters for TOC detection
- `min_start_page`: Optional[int] - minimum page for anchor search
- `bleed_threshold`: float (default 0.8) - ratio threshold for TOC bleed detection
- `field_name`: Optional[str] - for field-specific handling (indications_for_use has special validation)
- `manufacturer_rules`: Optional[Dict] - manufacturer-specific min pages, per-field overrides
- `toc_mask`: Optional[Sequence[int]] - pre-known TOC pages to skip
- `section_validator`: Optional[Callable[[Section], bool]] - custom validator

**Core Algorithm** (lines 520-710):

1. **TOC Filtering** (lines 520-538)
   ```python
   if toc_guard:
       working_pages, guard_report = strip_toc(working_pages, guard)
       # Collect dropped page numbers into toc_mask_set
   ```

2. **Minimum Page Enforcement** (lines 552-574)
   ```python
   # Check manufacturer_rules.get("min_anchor_page")
   # Check manufacturer_rules.get("fields").get(field_name).get("min_page")
   # Enforce: page >= min_page_threshold
   ```

3. **Anchor Pattern Compilation** (lines 587-597)
   ```python
   start_patterns = [_compile_anchor_pattern(anchor) for anchor in start_list]
   # Pattern: ^\s*(?:bullet\s*)?(?:\d+(?:\.\d+)*)?\s*{escaped_anchor}(?:\b|[:\-–—]|\s)
   ```

4. **Anchor Finding Loop** (lines 604-697)
   ```python
   while attempts < max_attempts and current_pages:
       candidate = _find_first_anchor_line(current_pages, start_patterns)
       if not candidate: break
       
       start_page_no, line_index, raw_line = candidate
       
       # Skip if in TOC mask
       if start_page_no in toc_mask_set: continue
       
       # Skip if before min_page
       if min_page_threshold and start_page_no < min_page_threshold: continue
       
       # Validate heading (not TOC-like, looks like section heading)
       if is_toc_like_para(raw_line) or not looks_like_section_heading(raw_line):
           current_pages = _drop_first_anchor_occurrence(...)
           continue
       
       # Extract section between start and stops
       extracted = slice_between(pages_for_slice, start_anchors=start_list, stop_anchors=stop_list)
       
       # Clean and validate
       cleaned = clean_paragraph(extracted)
       cleaned = _truncate_to_stop(cleaned, stop_list, start_tokens, field_name=field_name)
       cleaned = normalize_bullets(cleaned)
       trimmed_text, trimmed_prefix = trim_anchor_bleed(cleaned, ratio_threshold=bleed_threshold)
       
       # Post-extraction validation
       if not anchor_post_guard(trimmed_text): break  # TOC-like content
       
       if field_name == "indications_for_use" and not _contains_indication_phrase(trimmed_text):
           break  # Must contain indication keywords
       
       if _span_contains_toc(trimmed_text) and not window_applied:
           # Limit page window to prevent TOC bleed
           limited_pages = _limit_pages_to_window(pages_for_slice, start_page_no, window=3)
           pages_for_slice = limited_pages
           window_applied = True
           continue
       
       # Build section
       return Section(
           anchor=start_list[0],
           text=trimmed_text,
           start_page=start_page_no,
           end_page=_find_anchor_page(pages_for_slice, stop_list),
           lines=[...],
           trimmed_prefix=trimmed_prefix,
           toc_report=guard_report,
       )
   ```

5. **Section Validator** (line 688)
   - Custom validation for edge cases
   - Example: Indications for Intuitive docs must avoid TOC mask pages

**Key Helper Functions**:

- `_contains_indication_phrase()` (lines 1003-1011)
  - Checks for phrases: "indicated for", "intended for use", "intended to", "indications"
  - Fallback: if text >= 160 chars and >= 2 sentence marks, assume valid
  
- `anchor_post_guard()` (lines 846-861)
  - Checks first 10 lines (ANCHOR_TOC_WINDOW)
  - Fails if ratio of TOC-like lines >= ANCHOR_TOC_RATIO (0.4)
  - Uses `is_toc_like_para()` for detection

- `trim_anchor_bleed()` (lines 136-153)
  - Removes leading TOC/index text from section
  - Processes in 6-line blocks (BLOCK_MAX_LINES)
  - Drops blocks where ≥80% lines are TOC-like

---

### 2.5 TOC Detection & Guard
**File**: `/home/user/IP_assist_lite/medparse/ifu/toc_guard.py`
**Lines**: 1-276

#### Key Function: `apply_toc_guard()`

**Purpose**: Drop Table of Contents / Index pages from leading window

**Input**:
- `pages`: Sequence[PageData]
- `config`: TocGuardConfig

**Configuration** (lines 29-38):
```python
@dataclass
class TocGuardConfig:
    enabled: bool = True
    density_threshold: float = 0.65  # Min ratio of non-empty lines with TOC markers
    dot_leader_min: float = 0.20    # Min ratio of lines with "..." and page numbers
    page_number_ratio: float = 0.40 # Min ratio of lines ending with page number
    scan_page_limit: int = 15       # Only check first N pages
    min_dotted_lines: int = 2       # Absolute minimum dotted lines to trigger
    min_page_number_lines: int = 2  # Absolute minimum page number lines
```

**Algorithm** (lines 108-123):
```python
for idx, page in enumerate(pages):
    if idx < limit and _looks_like_toc_page(page, config):
        dropped.append(page.number)
        continue  # Skip page
    filtered.append(page)
```

#### Key Function: `_looks_like_toc_page()`

**Detection Rules** (lines 156-194):

1. **Explicit Keywords** (lines 165-167)
   ```python
   TOC_KEYWORDS = ("table of contents", "contents", "index", "indice", "summary of sections")
   if any(keyword in lowered_line for line in lowered_lines):
       return True
   ```

2. **Dotted Line Pattern** (lines 169-170)
   ```python
   DOT_LEADER_RE = r"\.{2,}\s*\d{1,3}\s*$"  # "Section Name.....123"
   dotted_lines = sum(1 for line if DOT_LEADER_RE.search(line))
   if dotted_lines >= config.min_dotted_lines and numbered >= config.min_page_number_lines:
       return True
   ```

3. **Density Check** (lines 183-184)
   ```python
   dotted_ratio = dotted_lines / total_lines
   numbered_ratio = numbered_lines / total_lines
   if dotted_ratio >= config.dot_leader_min and numbered_ratio >= config.page_number_ratio:
       return True
   ```

4. **Short Lines with Numbers** (lines 186-187)
   ```python
   if total_lines >= 4 and numbered_ratio >= 0.5 and short_lines/total_lines >= 0.7:
       return True
   ```

5. **Numbered Headings** (lines 190-192)
   ```python
   heading_hits = sum(1 for line if _looks_like_section_candidate(line))
   if total_lines >= 5 and heading_hits >= 4 and numbered_ratio >= 0.3:
       return True
   ```

#### Key Function: `trim_anchor_bleed()`

**Purpose**: Remove TOC text from START of extracted section

**Algorithm** (lines 197-243):
```python
def _compute_bleed_prefix(lines, max_blocks=3, ratio_threshold=0.8):
    drop = 0
    block = []
    block_count = 0
    
    while idx < total_lines and block_count < max_blocks:
        line = lines[idx]
        block.append(line)
        idx += 1
        
        # Complete block if blank line, >= 6 lines, or end of text
        if not line.strip() or len(block) >= 6 or idx == total_lines:
            non_empty = [c for c in block if c.strip()]
            
            if not non_empty:
                drop += len(block)
                block = []
                block_count += 1
                continue
            
            # Check if this block is TOC-like
            toc_lines = sum(1 for c in non_empty if _is_toc_line(c))
            ratio = toc_lines / len(non_empty)
            
            if ratio >= ratio_threshold:  # 80%+ is TOC
                drop += len(block)
                block = []
                block_count += 1
                continue
            
            break  # Stop - this block is real content
    
    return drop
```

---

### 2.6 Manufacturer-Specific Anchor Maps
**File**: `/home/user/IP_assist_lite/medparse/ifu/anchors.py`
**Lines**: 279-434

#### INTUITIVE_ANCHORS (lines 279-374)
```python
INTUITIVE_ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "indications_for_use": {
        "start": [
            "1.4.1 indications for use",
            "1.4 professional instructions for use",  # Navigate to parent first
            "indications for use",
        ],
        "stops": [
            "1.4.2 intended use",
            "intended use",
            "1.4.3 intended user",
            "clinical risks and benefits",
            "1.4.4 intended patient population",
            "contraindications",
            "warnings",
            "table 1.1",
        ],
    },
    # ... more fields
}
```

**Key Pattern**: 
- Section-numbered anchors (1.4.1, 1.4.2) for structured Ion manuals
- Fallbacks to plain text anchors

#### OLYMPUS_ANCHORS (lines 377-426)
```python
OLYMPUS_ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "indications_for_use": {
        "start": [
            "indications for use",
            "indication",
        ],
        "stops": [
            "contraindications",
            "contraindication",
            "important information — please read before use",
            "important information - please read before use",
            "user qualifications",
            "instruction manual",
            "warnings",
            "warning",
        ],
    },
    # ... more fields
}
```

---

## PART 3: TABLE EXTRACTION & FORMATTING

### 3.1 Table Ingestion
**File**: `/home/user/IP_assist_lite/medparse/ingest/tables.py`
**Lines**: 28-113

#### Key Function: `extract_tables()`

**Input**:
- `pdf_path`: Path to PDF
- `page_number`: int (1-based)
- `page_text`: str

**Logic**:
1. **Keyword Check** (lines 31-33)
   ```python
   TABLE_KEYWORDS = ("table", "status indicator", "led", "power button", 
                     "complication", "sensitivity", "specificity", "adverse event")
   lower_text = page_text.lower()
   if not any(keyword in lower_text for keyword in TABLE_KEYWORDS):
       return []
   ```

2. **PDFPlumber Extraction** (lines 38-51)
   ```python
   with pdfplumber.open(pdf_path) as pdf:
       page = pdf.pages[page_number - 1]
       for raw_table in page.extract_tables() or []:
           headers, rows = _split_table(raw_table)
           title = _detect_table_title(page_text, headers)
           found.append(TableData(title=title, headers=headers, rows=rows, page=page_number))
   ```

3. **Fallback to Inline Tables** (lines 52)
   ```python
   return _extract_inline_tables(page_text, page_number)
   ```

#### Key Function: `_split_table()` (lines 55-65)

```python
def _split_table(raw_table: List[List[Optional[str]]]) -> tuple[List[str], List[List[str]]]:
    # Normalize cells: strip and empty-string defaults
    normalized_rows = [
        [cell.strip() if isinstance(cell, str) else "" for cell in row]
        for row in raw_table
    ]
    headers = normalized_rows[0] if normalized_rows else []
    body = normalized_rows[1:] if len(normalized_rows) > 1 else []
    
    # Auto-generate headers if all empty
    if headers and all(not cell for cell in headers):
        headers = [f"col_{idx+1}" for idx in range(len(headers))]
    
    return headers, body
```

#### Key Function: `_detect_table_title()` (lines 68-87)

**Logic**:
1. Find lines starting with "table"
2. Look ahead for indicator keywords (complication, sensitivity, etc.)
3. Match full headers in page text
4. Return first candidate

---

### 3.2 Table Normalization (IFU)
**File**: `/home/user/IP_assist_lite/medparse/normalize/tables.py`
**Lines**: 1-137

#### Key Function: `clean_tables()`

**Input**: List of raw table dicts

**Processing Steps**:

1. **Filter Malformed** (lines 81-83)
   ```python
   filtered = [t for t in tables if isinstance(t, dict)]
   filtered = [t for t in filtered if t.get("title") or any(t.get("rows") or [])]
   ```

2. **Merge "(continued)" Tables** (lines 86-102)
   ```python
   CONT_RE = re.compile(r"\(continued\)", re.IGNORECASE)
   
   for table in filtered:
       title = str(table.get("title") or "").strip()
       base_title = CONT_RE.sub("", title).strip()
       
       if CONT_RE.search(title) and base_title in last_by_base:
           parent = last_by_base[base_title]
           parent["rows"].extend(table.get("rows", []))
           continue
   ```

3. **Deduplicate by Title** (lines 114-132)
   ```python
   dedup_map: Dict[str, Dict[str, object]] = {}
   
   for table in merged:
       if not _is_allowed(title, rows):  # Allowlist check
           continue
       
       title_key = normalize_title(title)  # Lowercase
       existing = dedup_map.get(title_key)
       
       if existing:
           if len(rows) > len(existing.get("rows") or []):
               dedup_map[title_key] = table  # Keep larger table
       else:
           dedup_map[title_key] = table
   ```

#### Allowlist Rules (lines 8-37)

```python
ALLOW_PREFIXES = [
    # Ion manual specific
    "table 4.2 led status indicator",
    "table 7.1 power modes",
    "table 6.1 system power",
    "table 6.2 input connections",
    "table b.1 sterilization",
    "table c.1 third-party compatibility",
    "table d.3 power specifications",
    # ... more
    
    # Generic patterns (lowercase for matching)
    "led", "power", "input", "sterilization", "compatibility",
    "specifications", "environmental", "symbols", "glossary",
]

def _is_allowed(title: str | None, rows: List[List[str]]) -> bool:
    normalized = normalize_title(title)
    
    # Check prefix matches
    if any(prefix in normalized for prefix in ALLOW_PREFIXES):
        return True
    
    # Reject if < MIN_DATA_ROWS (2)
    if len(rows) < MIN_DATA_ROWS:
        return False
    
    # Reject if title too short or missing
    if not title or len(title.strip()) < 5:
        return False
    
    return True
```

---

### 3.3 Table Classification (Articles)
**File**: `/home/user/IP_assist_lite/medparse/normalize/tables_classifier.py`
**Lines**: 67-160+

#### Key Function: `classify_and_gate_tables()`

**Three-Gate Validation**:

1. **Gate 1: Medical Headers** (line 86)
   ```python
   medical_headers = count_medical_headers(table_data.headers)
   if medical_headers < 2:
       continue  # Skip - not a medical table
   ```

2. **Gate 2: Paragraph Check** (lines 91-92)
   ```python
   if is_paragraph_table(table_data):
       continue  # Skip - abstract or prose mis-detected as table
   ```

3. **Gate 3: Size Check** (lines 94-96)
   ```python
   if len(table_data.headers) < 2 or len(table_data.rows) < 1:
       continue
   ```

4. **Gate 4: Cell Size Check** (line 98)
   ```python
   if cell_exceeds_character_limit(table_data):
       continue
   ```

#### Medical Glossary (lines 58-64)
```python
MEDICAL_GLOSSARY = [
    'n', '%', 'p-value', 'p value', 'ci', '95% ci', 'or', 'rr', 'hr',
    'age', 'sensitivity', 'specificity', 'auc', 'ppv', 'npv',
    'mean', 'median', 'sd', 'iqr', 'range', 'min', 'max',
    'total', 'patient', 'case', 'group', 'arm', 'control',
    'years', 'months', 'days', 'male', 'female',
]
```

#### Table Type Classification (lines 30-55)
```python
TABLE_TYPE_PATTERNS = {
    'diagnostic_accuracy': [
        'sensitivity', 'specificity', 'ppv', 'npv', 'auc', 'accuracy',
        'positive predictive value', 'negative predictive value',
        'roc', 'c-statistic'
    ],
    'baseline_characteristics': [
        'age', 'gender', 'sex', 'bmi', 'smoking', 'comorbidities',
        'baseline', 'demographics', 'characteristics'
    ],
    'complications': [
        'complication', 'adverse event', 'pneumothorax', 'bleeding',
        'mortality', 'death', 'ctcae', 'grade'
    ],
    'outcomes': [
        'outcome', 'survival', 'progression', 'response', 'recurrence',
        'follow-up', 'endpoint'
    ],
    'diagnostic_yield': [
        'yield', 'diagnostic', 'diagnosis', 'malignancy', 'adequacy'
    ],
}
```

---

### 3.4 EnhancedTable Schema
**File**: `/home/user/IP_assist_lite/medparse/schema/article.py`
**Lines**: 211-223

```python
class TableFootnote(MedparseModel):
    """Table footnote with symbol and text."""
    symbol: str  # *, †, ‡, a, b, etc.
    text: str

class EnhancedTable(MedparseModel):
    """Table with header stitching, stub columns, and footnotes."""
    
    id: str
    label: Optional[str] = None  # "Table 1", "Table 2a"
    caption: Optional[str] = None
    headers: List[List[str]] = Field(default_factory=list)  # Multi-row headers
    stub_column: Optional[int] = None  # Index of stub/row-header column
    rows: List[List[str]] = Field(default_factory=list)
    footnotes: List[TableFootnote] = Field(default_factory=list)
    page: Optional[int] = None
    table_type: Optional[str] = None  # From classifier
    truncated_cells: bool = False
```

#### Table Mapping (Article Extractor)
**File**: `/home/user/IP_assist_lite/medparse/extractors/article.py`
**Lines**: 823-835

```python
def _map_tables(blocks: Sequence[TableBlock]) -> List[EnhancedTable]:
    tables: List[EnhancedTable] = []
    for idx, block in enumerate(blocks, start=1):
        tables.append(
            EnhancedTable(
                id=f"table_{idx}",
                caption=block.caption,
                headers=[block.headers],  # ← Wraps in List for multi-row support
                rows=block.rows,
                page=block.page,
                table_type=block.table_type,
            )
        )
    return tables
```

---

## PART 4: CONFIGURATION & RUNTIME OVERRIDES

### 4.1 IFU Configuration
**File**: `/home/user/IP_assist_lite/configs/run_ifu.yaml`

#### Key Settings (lines 36-99):

**IFU-Specific Engine Config** (lines 36-60):
```yaml
ifu:
  small_ifu_threshold: 4          # Treat ≤4 page IFUs as "small"
  small_leaflet_policy: map_intended_use_to_indications
  ifu_engine: hybrid              # Default engine mode
  fast_long_docs: true            # Enable 2-pass for long docs
  long_doc_page_threshold: 80     # Pages > 80 trigger fast path
  fast_long_engine: pymupdf       # Use fast engine first
  
  engine:
    mode: auto
    text: pymupdf                 # Primary text extraction
    tables: pdfplumber            # Table extraction engine
    auto:
      sample_pages: 6             # Check first 6 pages for engine selection
      char_density_threshold: 1400 # Chars per page
      image_density_threshold: 0.6
      large_doc_pages: 90
      prefer: pymupdf
      fallback: pdfplumber
      timeouts:
        pymupdf: 70
        pdfplumber: 85
```

**TOC Guard Config** (lines 70-79):
```yaml
toc_guard:
  enabled: true
  density_threshold: 0.65
  dot_leader_min: 0.20
  page_number_ratio: 0.40
```

**Manufacturer Overrides** (lines 75-99):
```yaml
manufacturer_overrides:
  "INTUITIVE SURGICAL, INC.":
    toc_guard:
      density_threshold: 0.55    # More aggressive for Ion index
      dot_leader_min: 0.15
    strict_anchors: true
    require_cover_metadata: true
    min_anchor_page: 10          # Don't search before page 10
```

### 4.2 Article Configuration
**File**: `/home/user/IP_assist_lite/configs/run_article.yaml`

#### Key Differences from IFU (lines 1-60):

```yaml
doc_type: article
profile: enriched

metadata_sources:
  zotero_json: "data/zotero/my_library.json"  # ← Not in IFU

enrichment:
  use_zotero: true              # ← Article-specific
  min_title_match: 0.90
  prefer_doi: true

thresholds:
  guideline:
    min_recommendations: 8       # ← Article-specific
    grade_density: 0.7
  research:
    min_sections: 4
    min_chars: 25000
    require_diagnostic_yield: true

size_guards:
  keep_table_types:             # ← Table type filtering
    - diagnostic_accuracy
    - baseline
    - complications
    - yield
    - outcomes
```

---

## PART 5: TEXT PROCESSING UTILITIES

### 5.1 Shared Utilities
**File**: `/home/user/IP_assist_lite/medparse/extract/utils.py`

#### `load_pages()` (lines 14-23)
```python
def load_pages(pdf_path, *, engine="pymupdf", max_pages=None, ocr=False):
    return list(iter_pages(pdf_path, engine=engine, page_limit=max_pages, enable_ocr=ocr))
```

#### `collect_tables()` (lines 78-92)
```python
def collect_tables(pages: Sequence[PageData]) -> List[dict]:
    serialised: List[dict] = []
    for page in pages:
        for table in page.tables:
            serialised.append({
                "title": table.title,
                "headers": table.headers,
                "rows": table.rows,
                "page": page.number,
            })
    return serialised
```

#### `iter_section_windows()` (lines 26-36)
```python
def iter_section_windows(pages: Sequence[PageData]) -> Iterator[Tuple[Heading, Optional[Heading]]]:
    """Yield (current_heading, next_heading) pairs for section extraction."""
    headings: List[Heading] = []
    for page in pages:
        headings.extend([h for h in page.headings if h.kind == "section"])
    headings.sort(key=lambda h: (h.page, h.line_index))
    
    for idx, current in enumerate(headings):
        nxt = headings[idx + 1] if idx + 1 < len(headings) else None
        yield current, nxt
```

---

## SUMMARY: CRITICAL HEURISTICS & FAILURE MODES

### IFU Extraction Critical Points
1. **Front-matter extraction** relies on hardcoded manufacturer patterns (ERBE, Intuitive, Olympus)
2. **TOC guard** uses 5 independent detection rules - false negatives if none trigger
3. **Anchor bleed** detection trims leading content with 80% TOC-line threshold
4. **Indication phrase validation** requires keywords ("indicated for", "intended for") or ≥2 sentence marks
5. **Manufacturer rules** can enforce min_anchor_page to avoid false positives on large documents

### Article Table Formatting Critical Points
1. **headers wrapped as `[headers]`** in `_map_tables()` - supports multi-row but defaults to single
2. **Medical header validation** checks GLOSSARY words, min 2 required
3. **Paragraph rejection** prevents abstract mis-classification
4. **No markdown conversion** - tables output as row/header arrays in JSON
5. **No cell alignment or column width tracking** - raw cell text only

### Known Gaps
- **Table markdown rendering**: No built-in conversion to markdown pipe format
- **Multi-row header stitching**: Schema supports but extractor doesn't populate
- **Column alignment**: No tracking of column width or text alignment
- **Stub column detection**: Schema has stub_column field but not populated
- **Table footnote extraction**: Schema supports but footnotes not extracted
- **IFU small leaflet policy**: Configured but not fully implemented

