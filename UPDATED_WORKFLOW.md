# Updated Workflow - Post Environment Fixes (2025-10-28)

**Key Changes**:
- ✅ Use `medparse-py311` (NOT `ipass2` or `ipassist-py311`)
- ✅ Direct CLI extraction (no sidecar needed for basic use)
- ✅ Sidecar optional (only for API/service mode)
- ✅ Enriched profile working with UMLS

---

## 🎯 Quick Start (No Sidecar Needed)

### For Direct PDF Extraction (Most Common)

```bash
# 1. Activate the correct environment
conda activate medparse-py311

# 2. Navigate to IP_assist_lite
cd /home/rjm/projects/IP_assist_lite

# 3. Run preflight check (optional but recommended)
python scripts/dev/preflight.py

# 4. Extract documents directly
# Articles
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache

# IFUs
python -m medparse.cli extract-ifus \
  "data/Input pdfs/IFUs/pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched \
  --no-cache

# Textbooks
python -m medparse.cli extract-textbooks \
  "data/Input pdfs/Textbooks" \
  --out out/textbooks \
  --config configs/run_textbook.yaml \
  --profile enriched \
  --no-cache
```

**That's it!** No sidecar, no environment variables needed for basic extraction.

---

## 🔧 Advanced: With Medparse Sidecar (API Mode)

Use this workflow when you need:
- FastAPI endpoints for extraction
- Remote extraction service
- Integration testing with HTTP calls

### 0) Stop Any Conflicting Processes

```bash
# Kill anything on relevant ports
lsof -i :8099 -sTCP:LISTEN -t | xargs -r kill -9  # Medparse API
lsof -i :7860 -sTCP:LISTEN -t | xargs -r kill -9  # Gradio UI
lsof -i :7861 -sTCP:LISTEN -t | xargs -r kill -9  # Alt Gradio
lsof -i :7862 -sTCP:LISTEN -t | xargs -r kill -9  # Alt Gradio
```

### 1) Start Medparse Sidecar (FastAPI Service)

**Option A: Using medparse-py311** (recommended, same env)
```bash
# Terminal 1: Start API service
conda activate medparse-py311
cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling

# Start the FastAPI sidecar
uvicorn api.main:app --host 0.0.0.0 --port 8099 --reload

# Sanity check from another terminal:
curl -s http://127.0.0.1:8099/healthz
# Expect: {"ok":true} or similar
```

**Option B: Separate environment** (if you created medparse-docling-py311)
```bash
conda activate medparse-docling-py311
cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
uvicorn api.main:app --host 0.0.0.0 --port 8099 --reload
```

### 2) Configure Environment Variables (for tests using HTTP)

```bash
# Terminal 2: Where you'll run tests
conda activate medparse-py311
cd /home/rjm/projects/IP_assist_lite

# Point to the sidecar
export MEDPARSE_BASE_URL=http://127.0.0.1:8099
export MEDPARSE_API_KEY=my-secret-medparse-key-123

# Force HTTP transport and disable sinks during testing
export MEDPARSE_TRANSPORT=http
export APP_USE_NEO4J=false
export APP_USE_QDRANT=false

# Optional: Change auth header if sidecar uses Authorization instead of X-API-Key
# export MEDPARSE_AUTH_HEADER_NAME=Authorization

# Verify what pytest will see:
python - <<'PY'
import os
print("MEDPARSE_BASE_URL =", os.getenv("MEDPARSE_BASE_URL"))
print("MEDPARSE_API_KEY  =", os.getenv("MEDPARSE_API_KEY"))
print("MEDPARSE_TRANSPORT =", os.getenv("MEDPARSE_TRANSPORT"))
PY
```

### 3) Smoke Test the Sidecar

```bash
# Test with X-API-Key (default)
curl -s -X POST http://127.0.0.1:8099/extract \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: ${MEDPARSE_API_KEY}" \
  -d '{"doc_id":"ping","pdf":"SGVsbG8gTm90IGEgcmVhbCBQREYgYmFzZTY0IQ=="}' \
  | jq .

# Should return 200 with JSON response (stub for fake data)
```

### 4) Run Tests with HTTP Transport

```bash
cd /home/rjm/projects/IP_assist_lite

# Regenerate golden files
REGEN_GOLDENS=1 PYTHONPATH=src pytest \
  tests/integration/test_structured_extractors.py -q

# Run specific test
REGEN_GOLDENS=1 PYTHONPATH=src pytest \
  tests/integration/test_structured_extractors.py \
  -k "test_research_cryo_matches_golden_and_strict_rules"

# Run full test suite
pytest tests/integration/test_medparse_articles.py \
  tests/integration/test_medparse_ifu.py \
  tests/integration/test_medparse_textbook.py \
  tests/unit/test_normalizers.py \
  tests/unit/test_cli_batch.py -q
```

---

## 📋 Common Commands Quick Reference

### Extraction (Direct CLI - No Sidecar)

```bash
# Always from IP_assist_lite directory
cd /home/rjm/projects/IP_assist_lite
conda activate medparse-py311

# Single article
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched

# Batch articles
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched

# Single IFU
python -m medparse.cli extract-ifus \
  "data/Input pdfs/IFUs/pdf/Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched

# Batch IFUs
python -m medparse.cli extract-ifus \
  "data/Input pdfs/IFUs/pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched

# Textbook chapters
python -m medparse.cli extract-textbooks \
  "data/Input pdfs/Textbooks" \
  --out out/textbooks \
  --config configs/run_textbook.yaml \
  --profile enriched
```

### Using Makefile Targets

```bash
# Batch extraction using Make
make batch INPUT="data/Input pdfs/articles/pdf" OUTPUT=out/articles

# Run preflight checks
make preflight

# Run tests
make test

# Run tests with coverage
make cov
```

### Ingest into Neo4j + Qdrant (Full Pipeline)

```bash
conda activate medparse-py311
cd /home/rjm/projects/IP_assist_lite

# Ingest from PDFs
ipa_ingest --path "data/Input pdfs/**/*.pdf" --doc-type auto

# Or via module
PYTHONPATH=src python -m jobs.ingest_documents \
  --path "data/Input pdfs/**/*.pdf" \
  --doc-type auto

# Ingest from JSON (already extracted)
ipa_ingest --json "out/articles/*.json" --raw-dir "data/Input pdfs/articles/pdf"
```

### Docker Services (Qdrant + Neo4j)

```bash
# Start services
make graph-up

# Check status
docker ps

# Stop services
make graph-down

# Validate
make graph-validate
```

---

## 🔍 Troubleshooting

### "ModuleNotFoundError: No module named 'medparse'"

**Fix**: Reinstall in editable mode
```bash
conda activate medparse-py311
cd /home/rjm/projects/IP_assist_lite
pip install -e .
```

### "Can't find model 'en_core_sci_lg'"

**Fix**: Install scispaCy model
```bash
conda activate medparse-py311
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz

# Verify
python scripts/dev/preflight.py
```

### Sidecar returns 401 Unauthorized

**Fix**: Check API key matches
```bash
# In sidecar terminal - check what key it expects
grep -r "API_KEY" api/

# In client terminal - verify env var
echo $MEDPARSE_API_KEY

# If using Authorization header instead of X-API-Key:
export MEDPARSE_AUTH_HEADER_NAME=Authorization
```

### Sidecar returns 422 Validation Error

**Fix**: Payload format mismatch
```bash
# Sidecar expects: {"doc_id": "...", "pdf": "<base64>"}
# Check adapter is mapping correctly

# Debug payload
curl -s -X POST http://127.0.0.1:8099/extract \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: ${MEDPARSE_API_KEY}" \
  -d @- <<'EOF' | jq .
{
  "doc_id": "test-doc",
  "pdf": "JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PAovVHlwZSAvQ2F0YWxvZwovUGFnZXMgMiAwIFIKPj4KZW5kb2JqCjIgMCBvYmoKPDwKL1R5cGUgL1BhZ2VzCi9LaWRzIFszIDAgUl0KL0NvdW50IDEKPD4KZW5kb2JqCjMgMCBvYmoKPDwKL1R5cGUgL1BhZ2UKL1BhcmVudCAyIDAgUgovTWVkaWFCb3ggWzAgMCA2MTIgNzkyXQovQ29udGVudHMgNCAwIFIKPj4KZW5kb2JqCjQgMCBvYmoKPDwKL0xlbmd0aCA0NAo+PgpzdHJlYW0KQlQKL0YxIDI0IFRmCjEwMCA3MDAgVGQKKEhlbGxvIFdvcmxkKSBUagpFVAplbmRzdHJlYW0KZW5kb2JqCnhyZWYKMCA1CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIAowMDAwMDAwMDc0IDAwMDAwIG4gCjAwMDAwMDAxMzEgMDAwMDAgbiAKMDAwMDAwMDIyOCAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDUKL1Jvb3QgMSAwIFIKPj4Kc3RhcnR4cmVmCjMyMQolJUVPRgo="
}
EOF
```

### sklearn Version Warnings

**Expected** - These warnings are handled gracefully:
```
InconsistentVersionWarning: Trying to unpickle estimator TfidfTransformer
from version 1.1.2 when using version 1.7.2
```

**Fix** (optional): Retrain classifier with Patch 9
```bash
# TODO: Create scripts/train_doc_type.py
# For now, warnings are non-fatal and can be ignored
```

---

## 📊 Profiles Comparison

### fast_raw Profile
- ❌ No UMLS enrichment
- ❌ No relations extraction
- ❌ No guideline normalization
- ❌ No validators
- ✅ Faster extraction (~30% time savings)
- ✅ Smaller output (no entity/relation data)

### enriched Profile (Default)
- ✅ UMLS entity linking (biomedical NER)
- ✅ Relations extraction (outcome→intervention pairs)
- ✅ Guideline grade normalization (ATS/GRADE)
- ✅ Profile-aware validation (guidelines vs research)
- ✅ TOC bleed prevention
- ✅ Evidence bank pattern (when Patch 8 fully integrated)
- 🐌 Slower extraction (~2-3x vs fast_raw)
- 📦 Larger output (rich metadata)

**When to use each**:
- `fast_raw`: Quick triage, bulk processing, non-critical extractions
- `enriched`: Production, research, NLP/RAG pipelines, critical data

---

## 🎯 Key Takeaways

### What Changed from Old Workflow

| Old (Before Today) | New (After Fixes) |
|-------------------|-------------------|
| `conda activate ipass2` | `conda activate medparse-py311` |
| `conda activate ipassist-py311` | `conda activate medparse-py311` |
| Sidecar required for extraction | Sidecar **optional** (direct CLI works) |
| UMLS model often broken | UMLS with automatic fallback (lg→md→sm) |
| Binary wheel build failures | Binary wheels only, no Cython compilation |
| Unclear environment setup | One command: `make setup-enriched` |
| No preflight checks | `python scripts/dev/preflight.py` |

### Directory Structure Reminder

```
~/projects/
├── IP_assist_lite/              ← USE THIS for extraction work
│   ├── medparse/                ← Library (extraction engine)
│   ├── src/                     ← RAG, indexing, retrieval
│   ├── configs/                 ← Authoritative configs
│   ├── data/                    ← Input PDFs, output JSONs
│   └── scripts/                 ← Utilities, preflight
│
└── ip_knowledge/medparse/medparse-docling/  ← FastAPI wrapper (optional)
    ├── api/                     ← API endpoints
    └── medparse/                ← Thin wrapper around library
```

### Environment Status

**✅ Ready**: `medparse-py311` (Python 3.11.13)
- All patches 1-7 working
- UMLS linking tested
- Preflight checks passing
- Binary wheels only

**❌ Deprecated**: `ipass2`, `ipassist-py311`, `ipass2_py311`
- Not updated with today's fixes
- Can be removed to avoid confusion

---

*Last Updated: 2025-10-28*
*Branch: medparse-dockling_v3*
*Environment: medparse-py311*
