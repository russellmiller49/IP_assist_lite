# MEDPARSE CODEBASE EXPLORATION - COMPLETE REFERENCE

**Date**: 2025-11-11  
**Scope**: Comprehensive IFU and Article extraction logic analysis  
**Generated**: Claude Code exploration session

---

## DOCUMENTS CREATED

### 1. MEDPARSE_EXTRACTION_ANALYSIS.md (963 lines)
**Location**: `/home/user/IP_assist_lite/MEDPARSE_EXTRACTION_ANALYSIS.md`

Complete technical reference with:
- Entry points & CLI orchestration (Part 1)
- IFU extraction pipeline detailed (Part 2: 2.1-2.6)
- Table extraction & formatting (Part 3: 3.1-3.4)
- Configuration & runtime overrides (Part 4)
- Text processing utilities (Part 5)
- Critical heuristics & failure modes (Part 6)

**Use for**: Deep understanding of implementation details

---

### 2. EXTRACTION_ISSUES_SUMMARY.md (250 lines)
**Location**: `/home/user/IP_assist_lite/EXTRACTION_ISSUES_SUMMARY.md`

Executive summary with:
- Quick reference table of file locations & line numbers
- Critical issues in IFU extraction (4 major issues)
- Critical issues in article table formatting (3 major issues)
- Configuration critical points
- Extraction pipeline flow diagrams
- Priority recommendations for fixes
- Performance characteristics
- Debug tips

**Use for**: Understanding what's broken and how to fix it

---

## ABSOLUTE FILE PATHS (Quick Reference)

### IFU EXTRACTION
```
/home/user/IP_assist_lite/medparse/extractors/ifu.py          Lines 94-386    Main extractor
/home/user/IP_assist_lite/medparse/ifu/frontmatter.py         Lines 284-403   Metadata extraction
/home/user/IP_assist_lite/medparse/normalize/ifu_anchors.py   Lines 61-243    Clinical field lifting
/home/user/IP_assist_lite/medparse/ifu/anchors.py             Lines 504-711   Anchor slicing (core algorithm)
/home/user/IP_assist_lite/medparse/ifu/anchors.py             Lines 279-434   Manufacturer-specific anchors
/home/user/IP_assist_lite/medparse/ifu/toc_guard.py           Lines 95-276    TOC detection & guard
```

### ARTICLE EXTRACTION & TABLES
```
/home/user/IP_assist_lite/medparse/extractors/article.py           Line 823-835   Table mapping
/home/user/IP_assist_lite/medparse/ingest/tables.py                Lines 28-113   Table ingestion
/home/user/IP_assist_lite/medparse/normalize/tables.py             Lines 1-137    Table normalization (IFU)
/home/user/IP_assist_lite/medparse/normalize/tables_classifier.py  Lines 67-160+  Table classification (Articles)
/home/user/IP_assist_lite/medparse/schema/article.py               Lines 211-223  EnhancedTable schema
```

### CONFIGURATION
```
/home/user/IP_assist_lite/configs/run_ifu.yaml          Lines 36-99    IFU-specific config
/home/user/IP_assist_lite/configs/run_article.yaml      Lines 1-60     Article-specific config
```

### SHARED UTILITIES
```
/home/user/IP_assist_lite/medparse/extract/utils.py     Lines 14-110   Shared extraction helpers
/home/user/IP_assist_lite/medparse/cli.py               Lines 58-318    CLI entry points
```

---

## CRITICAL FUNCTIONS & ALGORITHMS

### IFU Extraction (in order of execution)

**1. Page Loading & Repair**
- `extract_ifu()` → line 107
- `repair_space_poor_pages()` → medparse/pipeline/engine_select.py
- Fixes character spacing issues in PDFs

**2. Manufacturer Detection**
- `detect_manufacturer()` → medparse/ifu/manufacturer.py
- Matches patterns for ERBE, Intuitive Surgical, Olympus

**3. Front-Matter Extraction**
- `extract_front_matter()` → `/home/user/IP_assist_lite/medparse/ifu/frontmatter.py:284-403`
- Extracts: manufacturer, product_name, part_number, revision, publication_date, model
- Key helpers: `_normalize_date()` (437-485), `_detect_manufacturer()` (412-419), `_select_product_name()` (497-566)

**4. Clinical Field Lifting (CRITICAL BOTTLENECK)**
- `lift_ifu_clinical_fields()` → `/home/user/IP_assist_lite/medparse/normalize/ifu_anchors.py:61-243`
- Extracts: indications_for_use, intended_use, contraindications, adverse_events, etc.
- Sub-steps:
  1. `resolve_toc_guard()` → Build TOC guard config
  2. `strip_toc()` → Apply TOC guard
  3. `resolve_anchor_map()` → Merge manufacturer-specific anchors
  4. For each field: `slice_section()` → Extract section text

**5. Anchor Slicing Algorithm (Core)**
- `slice_section()` → `/home/user/IP_assist_lite/medparse/ifu/anchors.py:504-711`
- Multi-level validation:
  1. TOC page filtering (lines 520-538)
  2. Minimum page enforcement (lines 552-574)
  3. Anchor pattern matching (lines 587-597)
  4. Heading validation (lines 617-620)
  5. Section extraction (lines 636-641)
  6. Text cleaning & trimming (lines 646-673)
  7. Post-extraction validation (lines 659-666)
  8. Section validator callback (lines 688-691)

**6. TOC Detection & Guard**
- `apply_toc_guard()` → `/home/user/IP_assist_lite/medparse/ifu/toc_guard.py:95-123`
- `_looks_like_toc_page()` → lines 156-194
- 5 detection rules (explicit keywords, dotted lines, density, short lines, numbered headings)

**7. Anchor Bleed Trimming**
- `trim_anchor_bleed()` → `/home/user/IP_assist_lite/medparse/ifu/anchors.py:136-153`
- Removes TOC text from section start
- Processes in 6-line blocks, drops if ≥80% are TOC-like

**8. Special Field Processing**
- `parse_contraindications()` → medparse/normalize/ifu_sections.py
- `sanitize_adverse_events()` → medparse/normalize/ifu_sections.py
- Converts text blocks to lists

**9. Table Collection**
- `collect_tables()` → `/home/user/IP_assist_lite/medparse/extract/utils.py:78-92`
- `clean_tables()` → `/home/user/IP_assist_lite/medparse/normalize/tables.py:66-134`
- Merges "(continued)" tables, deduplicates by title

---

### Article Table Extraction

**1. Table Ingestion**
- `extract_tables()` → `/home/user/IP_assist_lite/medparse/ingest/tables.py:28-53`
- Keyword gate: checks for "table", "complication", "sensitivity", etc.
- Uses PDFPlumber or falls back to inline extraction

**2. Table Classification & Gating**
- `classify_and_gate_tables()` → `/home/user/IP_assist_lite/medparse/normalize/tables_classifier.py:67-117`
- 4-gate validation:
  1. Medical headers >= 2 (line 86)
  2. Not paragraph-like (line 91)
  3. Size check: headers >= 2, rows >= 1 (lines 94-96)
  4. Cell size check (line 98)

**3. Table Type Classification**
- `classify_table_type()` → lines 105-115 (referenced, not shown)
- Types: diagnostic_accuracy, baseline_characteristics, complications, outcomes, diagnostic_yield, reasons_for_failure

**4. Table Mapping to EnhancedTable**
- `_map_tables()` → `/home/user/IP_assist_lite/medparse/extractors/article.py:823-835`
- Wraps TableBlock.headers in List for multi-row support
- Populates: id, caption, headers, rows, page, table_type

---

## KEY CONCEPTS & TERMINOLOGY

### IFU-Specific
- **Anchor**: Text phrase marking section start (e.g., "indications for use")
- **Stop anchor**: Text phrase marking section end (e.g., "intended use")
- **TOC bleed**: Table of Contents text incorrectly included in clinical field
- **Anchor bleed**: TOC-like content at start of extracted section
- **Indication phrase**: Keywords like "indicated for", "intended for use"
- **Manufacturer rule**: min_anchor_page, field-specific overrides

### Table-Specific
- **Medical glossary**: Keywords (n, %, CI, sensitivity, specificity) that validate tables
- **Stub column**: First column with row headers (not currently detected)
- **Cell truncation**: Long cells cut off with no indication
- **Multi-row headers**: Headers spanning multiple rows (schema supports, extraction doesn't)

### Extraction Pipeline
- **Gate**: Validation checkpoint that filters data
- **Bleed**: Unwanted content mixed with extracted section
- **Trim**: Remove content from start or end
- **Dedupe**: Remove duplicates based on key
- **Allowlist**: Whitelist of acceptable patterns

---

## COMMON ISSUES & SOLUTIONS

### IFU Issues

**Issue 1: Missing clinical fields**
- Cause: Indication phrase validation too strict (lines 663-665)
- Solution: Add fallback heuristics for technical documents

**Issue 2: TOC page misclassification**
- Cause: 5 independent rules, can fail if all miss
- Solution: Tune density thresholds per manufacturer

**Issue 3: Manufacturer-specific anchors incomplete**
- Cause: Only INTUITIVE_ANCHORS and OLYMPUS_ANCHORS defined
- Solution: Add more manufacturer rules or generic fallback

**Issue 4: Front-matter extraction for new manufacturers**
- Cause: Hardcoded patterns (lines 17-40) only cover 3 manufacturers
- Solution: Add config file for new patterns

### Article Table Issues

**Issue 1: Tables without medical headers rejected**
- Cause: Gate 1 requires >= 2 medical glossary words (line 86)
- Solution: Lower threshold or add domain-specific glossary

**Issue 2: Multi-row headers not extracted**
- Cause: _map_tables() wraps single row: headers=[block.headers] (line 830)
- Solution: Detect and preserve multi-row header structure

**Issue 3: No markdown rendering**
- Cause: No table-to-markdown converter implemented
- Solution: Add markdown generation function

**Issue 4: No column alignment tracking**
- Cause: Only text stored, no alignment/width metadata
- Solution: Add column type inference and alignment detection

---

## DEBUGGING WORKFLOW

### For IFU Extraction Issues

1. **Check if TOC was properly detected**:
   - Look at output JSON's `pipeline_info.toc_guard_applied`
   - Check `pipeline_info.toc_guard_pages_dropped` for dropped pages

2. **Check if manufacturer was detected**:
   - Look at `manufacturer` field in output
   - Check `pipeline_info.manufacturer_detection`

3. **Check which clinical fields failed**:
   - Look at `pipeline_info.anchor_bleed_errors`
   - Each error indicates a field that had TOC bleed

4. **Check anchor extraction spans**:
   - Look at `pipeline_info.toc_guard` → `section_spans`
   - Shows start_page and end_page for each field

5. **Trace validation failures**:
   - For indications_for_use: check if it has indication phrases
   - For any field: check if it starts with TOC-like lines

### For Article Table Issues

1. **Check table classification**:
   - Look at `table_type` field: should match one of 6 types
   - Look at confidence (not currently output)

2. **Check if table was gated**:
   - If expected table missing: check medical headers count
   - If abstract included as table: paragraph_table check failed

3. **Check header structure**:
   - Look at `headers` field: should be List[List[str]]
   - If empty: table had no headers

4. **Check for truncation**:
   - Look at `truncated_cells` flag
   - If true: some cells were cut off

---

## PERFORMANCE TIPS

### Speeding Up IFU Extraction

1. **Reduce page limit**: Pass `page_limit=50` to skip end sections
2. **Skip slow engines**: Set `ifu_engine: pymupdf` if pdfplumber times out
3. **Disable enrichment**: Use `profile: fast_raw` to skip detailed processing
4. **Tune TOC guard**: Increase density_threshold to skip more false positives
5. **Set min_anchor_page**: Use manufacturer rules to start anchor search at page 10+

### Speeding Up Article Extraction

1. **Limit pages**: Use `page_limit` parameter
2. **Skip table classification**: Not needed if only want text
3. **Skip Zotero enrichment**: Set `use_zotero: false`
4. **Use fast_raw profile**: Skips detailed extraction

---

## TESTING ENTRY POINTS

### Running IFU Extraction
```bash
# CLI
cd /home/user/IP_assist_lite
medparse extract-ifus input/ --out out/ifus

# Programmatic
from medparse.extractors.ifu import extract_ifu
doc = extract_ifu(Path("test.pdf"), engine="pymupdf")
```

### Running Article Extraction
```bash
# CLI
medparse extract-articles input/ --out out/articles

# Programmatic
from medparse.extractors.article import extract_article
doc = extract_article(Path("test.pdf"), engine="pymupdf")
```

---

## RELATED DOCUMENTATION

See also:
- `/home/user/IP_assist_lite/CLAUDE.md` - Project context and guidelines
- `/home/user/IP_assist_lite/ARTICLE_TEXTBOOK_HARDENING.md` - Article hardening phase 1
- `/home/user/IP_assist_lite/ARTICLE_TEXTBOOK_HARDENING_PHASE2.md` - Article hardening phase 2
- `/home/user/IP_assist_lite/ARCHITECTURE_CLARITY.md` - System architecture overview

---

## NEXT STEPS

1. **Fix IFU indication phrase validation**: Add heuristic fallbacks in `/home/user/IP_assist_lite/medparse/ifu/anchors.py:1003-1011`

2. **Expand manufacturer support**: Add new patterns to `/home/user/IP_assist_lite/medparse/ifu/frontmatter.py:MANUFACTURER_PATTERNS`

3. **Add article table markdown**: Implement table-to-markdown converter in `medparse/normalize/`

4. **Improve table column detection**: Add stub column detection in `medparse/normalize/tables_classifier.py`

5. **Extract table footnotes**: Add footnote parsing in `medparse/normalize/`

---

**Generated by Claude Code exploration - 2025-11-11**

For questions, reference the detailed analysis in MEDPARSE_EXTRACTION_ANALYSIS.md or the summary in EXTRACTION_ISSUES_SUMMARY.md.
