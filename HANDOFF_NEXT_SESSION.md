# Handoff for Next Claude Session

**Date**: 2025-10-28
**Branch**: `medparse-dockling_v3`
**Environment**: `medparse-py311` (Python 3.11.13)
**Repository**: `/home/rjm/projects/IP_assist_lite`

---

## 📋 Context: What Was Completed

### Session Goal
Implement environment fixes and Patches 1-9 from `IMPLEMENTATION_SUMMARY.md` to stabilize the medparse extraction library and reduce JSON output sizes.

### Status Summary
- ✅ **Patches 1-7**: COMPLETE (all core functionality working)
- 🚧 **Patch 8**: Foundation complete (85% - integration pending)
- 📋 **Patch 9**: Not started

### Environment Fixed
The `medparse-py311` conda environment is now:
- ✅ Using binary wheels only (no Cython compilation)
- ✅ Has scispaCy model `en_core_sci_lg-0.5.4` installed
- ✅ Correct versions pinned: sklearn 1.7.2, typer<0.10, scipy<1.11, spacy 3.7.4
- ✅ UMLS linking tested and working (6 entities found in test)
- ✅ Preflight checks passing

### Key Files to Reference

**Documentation Created (READ THESE FIRST)**:
1. `/home/rjm/projects/IP_assist_lite/IMPLEMENTATION_COMPLETE.md` - Comprehensive status of all patches
2. `/home/rjm/projects/IP_assist_lite/PATCH_STATUS.md` - Detailed patch tracking
3. `/home/rjm/projects/IP_assist_lite/UPDATED_WORKFLOW.md` - Complete workflow guide
4. `/home/rjm/projects/IP_assist_lite/QUICK_REFERENCE.md` - One-page command reference
5. `/home/rjm/projects/IP_assist_lite/ARCHITECTURE_CLARITY.md` - How medparse (library) and IP_assist_lite (runner) fit together

**User's Original Instructions**:
- `/home/rjm/projects/IP_assist_lite/CLAUDE.md` - Project instructions (always follow)
- `/home/rjm/projects/IP_assist_lite/ENVIRONMENT_CLEANUP.md` - User's cleanup instructions (what we implemented)

**Implementation Files**:
- `/home/rjm/projects/IP_assist_lite/medparse/schema/common.py` - Evidence bank schema
- `/home/rjm/projects/IP_assist_lite/medparse/utils/evidence_dedup.py` - EvidenceBank utility
- `/home/rjm/projects/IP_assist_lite/medparse/config.py` - Config with size_guards support
- `/home/rjm/projects/IP_assist_lite/configs/run_article.yaml` - Config with size guards
- `/home/rjm/projects/IP_assist_lite/medparse/validate/article_rules.py` - Profile-aware validation

---

## 🎯 Immediate Next Steps (Priority Order)

### 1. Integrate Evidence Bank into Pipeline (1-2 hours) ⭐ HIGH PRIORITY

**Goal**: Complete Patch 8 by integrating the evidence bank pattern into the extraction pipeline to achieve 10×-30× JSON size reduction.

**What's Already Done**:
- ✅ Schema: `EvidenceSpan.compute_hash()`, `evidence_bank` field on `BaseDocument`
- ✅ Utility: `medparse/utils/evidence_dedup.py` with `EvidenceBank` class
- ✅ Config: `size_guards` section in all `configs/run_*.yaml` files
- ✅ Models: `SizeGuards`, `TruncationNotice` in `medparse/schema/common.py`

**What Needs Integration**:

**File to Modify**: `/home/rjm/projects/IP_assist_lite/medparse/pipeline/run_extract.py`

**Changes Needed**:
1. Import at top:
   ```python
   from medparse.utils.evidence_dedup import EvidenceBank
   from medparse.schema.common import SizeGuards
   ```

2. In extraction function (after config loaded, before extractor called):
   ```python
   # Create evidence bank from config
   size_guards_dict = config.size_guards.to_dict() if hasattr(config, 'size_guards') else {}
   size_guards = SizeGuards(**size_guards_dict)
   evidence_bank = EvidenceBank(size_guards=size_guards)
   ```

3. Pass `evidence_bank` to extractors/normalizers as needed

4. At end of extraction (before returning document):
   ```python
   # Populate evidence bank
   document.evidence_bank = evidence_bank.get_bank()

   # Add truncation notice if any
   truncation_notice = evidence_bank.get_truncation_notice()
   if truncation_notice:
       document.truncation_notice = truncation_notice

   # Log stats
   stats = evidence_bank.get_stats()
   LOGGER.info(
       "Evidence deduplication: %d total, %d deduplicated, %d truncated",
       stats["total_added"],
       stats["deduplicated"],
       stats["truncated"],
   )
   ```

**Files to Update** (use evidence bank):
- `/home/rjm/projects/IP_assist_lite/medparse/extractors/article.py`
  - In outcome extraction: replace direct `EvidenceSpan` with `evidence_bank.add_evidence()`
  - In recommendation extraction: use `evidence_bank.add_evidence_list()`

- `/home/rjm/projects/IP_assist_lite/medparse/normalize/guideline_grades.py`
  - Pass `evidence_bank` parameter
  - Use `evidence_bank.add_evidence()` for recommendation evidence

**Testing**:
```bash
conda activate medparse-py311
cd /home/rjm/projects/IP_assist_lite

# Test on large guideline (currently 59 MB)
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf" \
  --out out/test \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache

# Check output size (should be 2-6 MB after integration)
ls -lh out/test/*.json

# Verify evidence_bank populated
jq '.evidence_bank | length' out/test/*.json
```

**Success Criteria**:
- ✅ JSON output size reduced by 10×-30×
- ✅ `evidence_bank` field populated with deduplicated evidence
- ✅ No information loss (all evidence stored once)
- ✅ `truncation_notice` present if any content was truncated

---

### 2. Retrain Document Type Classifier (1 hour) ⭐ MEDIUM PRIORITY

**Goal**: Eliminate sklearn version warnings by retraining classifier on current sklearn 1.7.2.

**Current Issue**:
```
InconsistentVersionWarning: Trying to unpickle estimator TfidfTransformer
from version 1.1.2 when using version 1.7.2
```

**What's Already Done**:
- ✅ Version-safe loading in `/home/rjm/projects/IP_assist_lite/medparse/classify/model.py`
- ✅ Graceful fallback to rules if model fails
- ✅ Tool script exists: `/home/rjm/projects/IP_assist_lite/tools/rebuild_vectorizer.py`

**What Needs Creation**:

**New File**: `/home/rjm/projects/IP_assist_lite/scripts/train_doc_type.py`

**Implementation**:
```python
#!/usr/bin/env python3
"""Train document type classifier on current sklearn version."""

import json
import joblib
from pathlib import Path
from sklearn.pipeline import make_pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import sklearn

def load_training_data():
    """Load training examples from labeled PDFs."""
    # Option 1: Use existing output JSONs as labeled data
    # Option 2: Create minimal labeled set manually
    # Option 3: Use folder structure (data/train/guideline/*.txt, etc.)

    X = []  # List of text strings
    y = []  # List of labels: "guideline", "research", "review", "ifu", "textbook"

    # TODO: Implement loading based on available data

    return X, y

def train_classifier(X, y):
    """Train TfidfVectorizer + LogisticRegression."""
    pipe = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_df=0.95),
        LogisticRegression(max_iter=2000, class_weight="balanced", n_jobs=-1)
    )
    pipe.fit(X, y)
    return pipe

def save_bundle(pipe, output_dir):
    """Save model bundle with version metadata."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save model
    joblib.dump(pipe, output_dir / "doc_type_sklearn.joblib", compress=3)

    # Save metadata
    meta = {
        "sklearn_version": sklearn.__version__,
        "schema_version": "v1",
        "labels": ["guideline", "research", "review", "ifu", "textbook"],
    }
    (output_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    print(f"✓ Saved model to {output_dir}")
    print(f"  sklearn version: {sklearn.__version__}")

if __name__ == "__main__":
    X, y = load_training_data()
    print(f"Loaded {len(X)} training examples")

    pipe = train_classifier(X, y)
    save_bundle(pipe, "models/doc_type")
```

**Testing**:
```bash
# After training
python scripts/train_doc_type.py

# Verify warnings gone
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf" \
  --out out/test \
  --profile enriched 2>&1 | grep -i "inconsistent"
# Should return nothing
```

**Success Criteria**:
- ✅ No sklearn version warnings
- ✅ Model file exists: `models/doc_type/doc_type_sklearn.joblib`
- ✅ Metadata file exists: `models/doc_type/meta.json`
- ✅ Classification accuracy ≥90% (if you have labeled data)

---

### 3. Test End-to-End (30 minutes)

**Goal**: Verify no regressions and all features working.

**Test Commands**:
```bash
conda activate medparse-py311
cd /home/rjm/projects/IP_assist_lite

# 1. Preflight
python scripts/dev/preflight.py

# 2. Guideline (should have doc_subtype="guideline")
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache

# Verify:
jq '.doc_subtype, (.recommendations | length), (.evidence_bank | length)' out/articles/article_combined*.json

# 3. Research article (should have doc_subtype="research")
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache

# Verify:
jq '.doc_subtype, .diagnostic_yield' out/articles/article_robotic*.json

# 4. IFU (should have no TOC contamination)
python -m medparse.cli extract-ifus \
  "data/Input pdfs/IFUs/pdf/Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched \
  --no-cache

# Verify:
jq '.front_matter' out/ifus/ifu_ion*.json
```

---

## 🔧 Environment Setup (For New Session)

```bash
# 1. Activate correct environment
conda activate medparse-py311

# 2. Navigate to repo
cd /home/rjm/projects/IP_assist_lite

# 3. Verify everything works
python scripts/dev/preflight.py

# 4. Check branch
git branch --show-current
# Should show: medparse-dockling_v3

# 5. See recent commits
git log --oneline -5
```

---

## 📚 Key Architectural Concepts

### medparse (library) vs IP_assist_lite (runner)

**medparse/** = Library (extraction engine)
- Schemas (`medparse/schema/`)
- Extractors (`medparse/extractors/`)
- Normalizers (`medparse/normalize/`)
- Validators (`medparse/validate/`)
- Pipeline orchestrator (`medparse/pipeline/run_extract.py`)

**IP_assist_lite** = Runner (orchestration + RAG)
- Configs (`configs/*.yaml`) ← Authoritative
- CLI (`medparse/cli.py`)
- RAG components (`src/`)
- Makefile, scripts

**Key Principle**: Library knows *how* to extract, configs define *what*.

### Evidence Bank Pattern (Patch 8)

**Problem**: Articles generate 59 MB JSONs because evidence text is repeated for every outcome/recommendation.

**Solution**: Central evidence bank with hash-based deduplication.

**Before**:
```json
{
  "outcomes": [
    {"name": "Pneumothorax", "evidence": {"text": "long repeated text...", "page": 5}},
    {"name": "Bleeding", "evidence": {"text": "long repeated text...", "page": 5}}
  ]
}
```

**After**:
```json
{
  "evidence_bank": {
    "abc123": {"text": "long text...", "page": 5}
  },
  "outcomes": [
    {"name": "Pneumothorax", "evidence_refs": ["abc123"]},
    {"name": "Bleeding", "evidence_refs": ["abc123"]}
  ]
}
```

**Expected Impact**: 10×-30× smaller JSONs (59 MB → 2-6 MB).

---

## ⚠️ Important Notes

### Environment
- ✅ **Use**: `medparse-py311` (Python 3.11.13)
- ❌ **Don't use**: `ipass2`, `ipassist-py311`, `ipass2_py311` (deprecated)

### Directory
- ✅ **Work from**: `/home/rjm/projects/IP_assist_lite`
- ℹ️ **Optional**: `/home/rjm/projects/ip_knowledge/medparse/medparse-docling` (FastAPI wrapper, not needed for extraction)

### Branch
- ✅ **Current**: `medparse-dockling_v3`
- All work committed and ready to continue

### Sidecar
- ℹ️ **Not required** for basic extraction (direct CLI works)
- ℹ️ **Optional** for API mode or HTTP-based testing

---

## 🐛 Known Issues (Non-Critical)

1. **sklearn warnings**: Expected until Patch 9 completed (non-fatal)
2. **pydantic warning**: `Field "model_name" has conflict with protected namespace` (cosmetic)
3. **spacy warning**: `FutureWarning: Possible set union at position 6328` (cosmetic)
4. **typer/docling conflict**: `docling requires typer>=0.12.5 but we have 0.9.4` (expected, medparse takes precedence)

All warnings are handled gracefully and don't block functionality.

---

## 📝 Commands for Next Session

**Start work**:
```bash
conda activate medparse-py311
cd /home/rjm/projects/IP_assist_lite
git status
python scripts/dev/preflight.py
```

**Quick test extraction**:
```bash
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf" \
  --out out/test \
  --profile enriched
```

**Check what needs integration**:
```bash
# Evidence bank schema exists:
grep -n "evidence_bank" medparse/schema/common.py

# Utility exists:
cat medparse/utils/evidence_dedup.py

# Config support exists:
grep -n "size_guards" medparse/config.py

# Integration point (needs work):
grep -n "def run_extract" medparse/pipeline/run_extract.py
```

---

## 🎯 Success Criteria for Next Session

1. ✅ Evidence bank integrated into pipeline
2. ✅ Test extraction produces JSONs with populated `evidence_bank`
3. ✅ JSON sizes reduced 10×-30× (59 MB → 2-6 MB)
4. ✅ Optional: Classifier retrained on sklearn 1.7.2

---

**All documentation, code changes, and tests are in the repo on branch `medparse-dockling_v3`. Environment is ready. Just continue from Step 1 above!** 🚀
