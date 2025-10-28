# Quick Reference Card - IP Assist Lite

**Environment**: `medparse-py311` (Python 3.11.13)
**Branch**: `medparse-dockling_v3`
**Directory**: `/home/rjm/projects/IP_assist_lite`

---

## 🚀 Most Common Commands

### 1. Setup & Verification
```bash
conda activate medparse-py311
cd /home/rjm/projects/IP_assist_lite
python scripts/dev/preflight.py
```

### 2. Extract Single Article (Enriched)
```bash
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched
```

### 3. Extract All Articles
```bash
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched
```

### 4. Extract IFUs
```bash
python -m medparse.cli extract-ifus \
  "data/Input pdfs/IFUs/pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched
```

### 5. Check Output
```bash
ls -lh out/articles/*.json
jq . out/articles/article_*.json | head -50
```

---

## ⚡ One-Liners

```bash
# Preflight check
conda activate medparse-py311 && python scripts/dev/preflight.py

# Test UMLS (quick)
conda activate medparse-py311 && python -c "import spacy; nlp = spacy.load('en_core_sci_lg'); print('✓ Model loaded')"

# Extract + view first result
python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf" --out out/test --profile enriched && jq .title out/test/*.json

# Count extracted files
ls out/articles/*.json | wc -l
```

---

## 🎯 Decision Tree

```
Need to extract PDFs?
  └─> Use: python -m medparse.cli extract-[articles|ifus|textbooks]
       ├─> enriched profile: Full UMLS, relations, validation
       └─> fast_raw profile: Quick extraction, no enrichment

Need API service?
  └─> Start sidecar: cd medparse-docling && uvicorn api.main:app --port 8099
       └─> Then use HTTP client

Need to test?
  └─> pytest tests/integration/test_*.py

Need to ingest into Neo4j/Qdrant?
  └─> ipa_ingest --path "data/Input pdfs/**/*.pdf" --doc-type auto
```

---

## ❓ Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: medparse` | `pip install -e .` |
| `Can't find model 'en_core_sci_lg'` | `make setup-enriched` or see UPDATED_WORKFLOW.md |
| `Wrong environment active` | `conda activate medparse-py311` |
| `Output JSON too large` | Wait for Patch 8 integration (evidence bank) |
| `sklearn warnings` | Expected, non-fatal (Patch 9 will fix) |

---

## 📚 Documentation

- **[UPDATED_WORKFLOW.md](UPDATED_WORKFLOW.md)** - Complete workflow guide
- **[IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md)** - What's done, what's pending
- **[ARCHITECTURE_CLARITY.md](ARCHITECTURE_CLARITY.md)** - How medparse (library) and IP_assist_lite (runner) fit together
- **[PATCH_STATUS.md](PATCH_STATUS.md)** - Detailed patch tracking

---

## 🔑 Key Facts

✅ **Environment**: `medparse-py311` (Python 3.11.13)
✅ **Patches 1-7**: Complete and tested
🚧 **Patch 8**: Foundation ready (evidence bank pattern)
📋 **Patch 9**: Not started (classifier retraining)

**UMLS Model**: `en_core_sci_lg-0.5.4` (with lg→md→sm fallback)
**Configs**: `configs/run_*.yaml` (authoritative)
**Profile**: `enriched` (default) or `fast_raw`

---

## 🎓 Examples

### Extract Guideline (Relaxed Validation)
```bash
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched

# Check: doc_subtype should be "guideline"
jq .doc_subtype out/articles/article_combined*.json
```

### Extract Research Article (Strict ATS)
```bash
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched

# Check: diagnostic_yield should have numerator/denominator
jq .diagnostic_yield out/articles/article_robotic*.json
```

### Extract Ion IFU (Manufacturer-Specific Rules)
```bash
python -m medparse.cli extract-ifus \
  "data/Input pdfs/IFUs/pdf/Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched

# Check: front_matter should have part_number, revision, model_name
jq .front_matter out/ifus/ifu_ion*.json
```

---

*Last Updated: 2025-10-28*
