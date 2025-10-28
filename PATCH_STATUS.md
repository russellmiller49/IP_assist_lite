# Patch Implementation Status - medparse-dockling_v3

Generated: 2025-10-28 after merging infra/env-guards-and-profile-sanity

## ✅ Completed Patches

### Infrastructure (from infra branch)
- ✅ Environment setup with binary wheels (sklearn 1.3-1.7.x, typer<0.10, scipy<1.11)
- ✅ Preflight checks ([scripts/dev/preflight.py](scripts/dev/preflight.py))
- ✅ UMLS model fallback (lg→md→sm) with graceful degradation
- ✅ Version-safe sklearn unpickling with warnings
- ✅ Make targets: `setup-enriched`, `preflight`
- ✅ Documentation: [README.md](README.md), [ARCHITECTURE_CLARITY.md](ARCHITECTURE_CLARITY.md)

### Patch 1: Profile-Aware Validation ✅
**Status**: COMPLETE

**Files**:
- ✅ [medparse/schema/article.py](medparse/schema/article.py:157) - `doc_subtype` field exists
- ✅ [medparse/extractors/article.py](medparse/extractors/article.py:86) - `_infer_doc_subtype()` called
- ✅ [medparse/validate/article_rules.py](medparse/validate/article_rules.py) - Profile-aware validation
- ✅ [configs/run_article.yaml](configs/run_article.yaml) - Thresholds configured

**Validation Logic**:
```yaml
guideline:
  min_recommendations: 8
  min_sections: 1
  require_ats_yield: false

research:
  min_sections: 4
  require_ats_yield: true
```

### Patch 2: Recommendation Parsing & Grade Normalization ✅
**Status**: COMPLETE

**Files**:
- ✅ [medparse/normalize/guideline_grades.py](medparse/normalize/guideline_grades.py:29) - `parse_guideline_recommendations()` exists
- ✅ [medparse/extractors/article.py](medparse/extractors/article.py:262) - Called when `enable_guideline_norms=true`
- ✅ Schema: `GuidelineRecommendation` with `grade`, `statement_type`, `evidence`

### Patch 3: UMLS Linking ✅
**Status**: COMPLETE (from infra branch)

**Files**:
- ✅ [medparse/normalize/umls_linking.py](medparse/normalize/umls_linking.py:198-232) - Model fallback implemented
- ✅ [medparse/config.py](medparse/config.py:32) - `UMLS_MODEL` env var support
- ✅ Graceful degradation when models unavailable

**Test Results**:
```
✓ Loaded scispaCy model: en_core_sci_lg (version 0.5.4)
✓ Status: linked
✓ Entities found: 6 (Bronchoscopy, airways, medical procedure)
```

## 🔍 Needs Verification

### Patch 4: Layout Hardening (TOC, 2-column, table gating)
**Status**: NEEDS CHECK

**Expected Files**:
- `medparse/normalize/layout.py` - is_toc_page(), gutter_aware_reflow()
- `medparse/normalize/tables_classifier.py` - Medical header detection

**Action**: Check if TOC bleed prevention exists

### Patch 5: ATS Yield Guard (research only)
**Status**: NEEDS CHECK

**Expected**:
- [medparse/normalize/article_yield_ats.py](medparse/normalize/article_yield_ats.py) - Back-solve logic
- Should populate `exclusion_reasons` instead of hard fail
- Validator enforces research gates

**Action**: Verify back-solve logic and research-only enforcement

### Patch 6: IFU Anchors + TOC Guard
**Status**: NEEDS CHECK

**Expected**:
- [medparse/normalize/ifu_anchors.py](medparse/normalize/ifu_anchors.py) - extract_clinical_block()
- [medparse/extractors/ifu.py](medparse/extractors/ifu.py) - Calls anchor extractor
- [medparse/validate/ifu_rules.py](medparse/validate/ifu_rules.py) - Manufacturer-specific rules

**Action**: Check if TOC contamination is prevented

### Patch 7: Textbook Chapters
**Status**: NEEDS CHECK

**Expected**:
- [medparse/extractors/textbook.py](medparse/extractors/textbook.py) - _load_book_metadata()
- `medparse/normalize/textbook_anchors.py` - Hierarchical sections
- `medparse/validate/textbook_rules.py` - Coverage ≥80%

**Action**: Verify book metadata loading

## ❌ Not Yet Implemented

### Patch 8: Output Size Guards (Evidence Bank Pattern)
**Status**: TODO

**Requirements**:
- Add `evidence_bank: Dict[str, EvidenceSpan]` to root schema
- Outcomes/recommendations store `evidence_refs: List[str]` (hashes)
- Size guards in config:
  ```yaml
  size_guards:
    max_evidence_per_item: 3
    max_chars_per_evidence: 1200
    max_tables: 50
    max_table_cells: 5000
  ```

**Files to Create/Modify**:
- [medparse/schema/common.py](medparse/schema/common.py) - Add EvidenceStore
- [medparse/pipeline/run_extract.py](medparse/pipeline/run_extract.py) - Implement deduplication
- [medparse/normalize/text_cleanup.py](medparse/normalize/text_cleanup.py) - Trim logic
- All `configs/run_*.yaml` - Add size_guards section

**Expected Impact**: 10×-30× smaller JSON files

### Patch 9: Retrain Document Type Classifier
**Status**: TODO

**Requirements**:
- Create [scripts/train_doc_type.py](scripts/train_doc_type.py)
- Train TfidfVectorizer + LinearSVC on sklearn 1.7.2
- Save bundle with version metadata
- Eliminate `InconsistentVersionWarning`

**Files**:
- `scripts/train_doc_type.py` (new)
- `models/doc_type/doc_type_sklearn.joblib` (new)
- `models/doc_type/meta.json` (new)
- [medparse/classify/model.py](medparse/classify/model.py:20-27) - Already has version check

## Next Actions

1. **Verify Patches 4-7**: Check existing code for TOC guards, IFU anchors, textbook metadata
2. **Implement Patch 8**: Evidence bank pattern for size reduction
3. **Implement Patch 9**: Retrain classifier on current sklearn
4. **Test Suite**: Run enriched extraction on all document types
5. **Validate**: Ensure no regressions, JSON sizes reasonable

## Test Commands

```bash
# Preflight
conda activate medparse-py311
python scripts/dev/preflight.py

# Guideline (enriched)
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf" \
  --out out/articles --config configs/run_article.yaml --profile enriched --no-cache

# Research (ATS)
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf" \
  --out out/articles --config configs/run_article.yaml --profile enriched --no-cache

# IFU (Intuitive)
python -m medparse.cli extract-ifus \
  "data/Input pdfs/IFUs/pdf/Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf" \
  --out out/ifus --config configs/run_ifu.yaml --profile enriched --no-cache
```

---
*Branch: medparse-dockling_v3 (after infra merge)*
