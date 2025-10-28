# IP Assist Lite - Dependency Structure

**Last Updated**: 2025-10-28
**Environment**: `medparse-py311` (Python 3.11.13)
**Branch**: `medparse-dockling_v3`

---

## 📦 Package Structure

### Core Packages (This Repository)

```
IP_assist_lite/
├── medparse/              # Main extraction library
│   ├── cli.py            # CLI commands (python -m medparse.cli)
│   ├── pipeline/         # Extraction pipeline
│   ├── extractors/       # Document-specific extractors
│   ├── schema/           # Pydantic models
│   ├── normalize/        # Text normalization
│   ├── umls/             # UMLS entity linking
│   └── utils/            # Utilities (evidence_dedup, cache, etc.)
├── src/                  # RAG/Graph components
│   ├── graph/            # Neo4j graph operations
│   ├── jobs/             # Ingestion jobs
│   └── adapters/         # External API adapters
└── scripts/              # Utility scripts
    ├── batch_extract_articles.py
    ├── batch_extract_ifus.py
    ├── batch_extract_textbooks.py
    └── batch_extract_all.py
```

**Installed as**: `ip-assist-lite` (editable install: `pip install -e .`)
**Import path**: `from medparse.pipeline.run_extract import run_extract`

---

## 🔗 External Packages

### Optional Sidecar (Separate Repository)

```
ip_knowledge/medparse/medparse-docling/
├── api/                  # FastAPI endpoints
│   ├── main.py          # API server
│   └── routes/          # API routes
└── medparse_api/        # Thin wrapper (not 'medparse'!)
```

**Installed as**: `medparse-api` (editable install: `pip install -e .`)
**Import path**: `from api.main import app` (no collision with medparse library)
**Purpose**: Optional HTTP API wrapper for extraction services
**Status**: Not required for direct CLI usage

---

## 📋 Dependency Categories

### 1. Core Dependencies (Required)

**PDF Processing**
```python
PyMuPDF==1.24.9              # Fast PDF text extraction (fitz)
PyMuPDFb==1.24.9             # Binary support for PyMuPDF
pdfplumber==0.11.7           # Table extraction, layout analysis
pypdfium2==4.30.0            # Alternative PDF rendering
```

**Text Processing**
```python
regex>=2023.0.0              # Advanced regex patterns
rapidfuzz>=3.0.0             # Fuzzy string matching
python-dateutil>=2.8.2       # Date parsing
```

**Data & ML**
```python
numpy>=1.24.0                # Numerical computing
pandas>=2.0.0                # Data manipulation
scikit-learn>=1.3,<1.8       # ML models (binary wheels only!)
scipy<1.11                   # Scientific computing (scispacy requirement)
torch>=2.0.0                 # Deep learning framework
```

**NLP - Base**
```python
spacy>=3.7.3,<3.8.0          # Core NLP library
spacy-legacy==3.0.12         # Legacy components
spacy-loggers==1.0.5         # Logging utilities
```

**Schema & Validation**
```python
pydantic>=2.0.0              # Data validation
pydantic_core==2.20.1        # Rust core for pydantic
pydantic-settings==2.4.0     # Settings management
```

**CLI & UI**
```python
typer>=0.9.0,<0.10           # CLI framework (spaCy 3.7.4 constraint)
click==8.3.0                 # CLI utilities (typer dependency)
rich>=13.0.0                 # Terminal formatting
tqdm>=4.65.0                 # Progress bars
```

**Testing**
```python
pytest>=8.0.0                # Testing framework
pytest-cov>=4.1.0            # Coverage reporting
hypothesis>=6.82.0           # Property-based testing
jsondiff>=2.0.0              # JSON comparison for tests
```

**API/Web** (Always installed, optional usage)
```python
fastapi>=0.110.0             # Web framework
uvicorn==0.30.6              # ASGI server
httpx==0.27.2                # HTTP client
```

**Vector Database**
```python
qdrant-client>=1.8,<1.16     # Vector search client
```

---

### 2. Enriched Profile Dependencies (Optional)

**Install with**: `pip install -e ".[enriched]"`

**UMLS Entity Linking**
```python
scispacy==0.5.4              # Biomedical NLP extensions
nmslib>=2.1.1                # Approximate nearest neighbor search
```

**scispaCy Models** (Installed separately)
```bash
# Large model (recommended for production)
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz

# Medium model (fallback)
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_md-0.5.4.tar.gz

# Small model (minimal)
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz
```

**Transformer Models** (Auto-downloaded by transformers library)
```python
sentence-transformers==5.1.1 # Sentence embeddings
transformers==4.56.2         # HuggingFace transformers
tokenizers==0.21.0           # Fast tokenization
torchvision==0.23.0          # Vision models (torch dependency)
```

**What Enriched Profile Enables**:
- ✅ UMLS entity linking (CUI, semantic types)
- ✅ Biomedical named entity recognition (NER)
- ✅ Medical concept normalization
- ✅ Relation extraction (outcome→intervention)
- ✅ Guideline grade normalization (ATS, GRADE)

**What Fast_Raw Profile Disables**:
- ❌ No UMLS enrichment
- ❌ No relation extraction
- ❌ No guideline normalization
- ✅ 30% faster extraction
- ✅ Smaller output files

---

### 3. Graph Database Dependencies (Optional)

**Install with**: `pip install -e ".[graph]"`

```python
neo4j>=5.20                  # Neo4j Python driver
```

**Docker Services** (Not Python packages)
```bash
# Started with docker-compose or Makefile
make graph-up                # Start Neo4j + Qdrant containers

# Neo4j: bolt://localhost:7687
# Qdrant: http://localhost:6333
```

---

### 4. Development Dependencies (Optional)

**Install with**: `pip install -e ".[dev]"`

```python
black>=24.0.0                # Code formatting
ruff>=0.4.0                  # Fast linter
isort>=5.12.0                # Import sorting
mypy>=1.8.0                  # Type checking
pre-commit>=3.6.0            # Git hooks
```

---

## 🔧 Version Constraints & Why They Matter

### Critical Constraints

**1. scikit-learn: `>=1.3,<1.8`**
- ✅ Versions 1.3-1.7.x use **binary wheels** (fast install, no compilation)
- ❌ Versions <1.3 or >=1.8 may require **source builds** (Cython, C compiler needed)
- ⚠️ Current warning: Model trained on 1.1.2, running on 1.7.2 (non-fatal, Patch 9 will fix)

**2. typer: `>=0.9,<0.10`**
- ✅ spaCy 3.7.4 requires typer <0.10
- ❌ typer 0.10+ breaks spaCy CLI commands

**3. scipy: `<1.11`**
- ✅ scispacy 0.5.4 requires scipy <1.11
- ❌ Newer scipy versions break scispacy compatibility

**4. spacy: `>=3.7.3,<3.8.0`**
- ✅ scispacy 0.5.4 is built for spaCy 3.7.x
- ❌ spaCy 3.8+ is incompatible with scispacy 0.5.4

**5. PyMuPDF: `==1.24.9`**
- ✅ Pinned to ensure consistent PDF parsing behavior
- ⚠️ Newer versions may change layout detection

---

## 🌍 Environment Setup

### One Environment to Rule Them All

**Environment Name**: `medparse-py311`
**Python Version**: 3.11.13

```bash
# Create environment
conda create -n medparse-py311 python=3.11 -y
conda activate medparse-py311

# Install pinned wheels (avoid source builds)
pip install "scikit-learn>=1.3,<1.8" \
            "spacy==3.7.4" \
            "scispacy==0.5.4" \
            "typer>=0.9,<0.10" \
            "PyMuPDF==1.24.9" \
            "scipy<1.11"

# Install scispaCy model (critical!)
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz

# Install main package (editable)
cd ~/projects/IP_assist_lite
pip install -e .

# Optional: Install sidecar (editable, separate package name)
cd ~/projects/ip_knowledge/medparse/medparse-docling
pip install -e .

# Verify
python scripts/dev/preflight.py
```

---

## 📊 Installed Package List (Current)

### Core (3 packages)
```
ip-assist-lite          0.1.0   # This repository
medparse                0.1.0   # Library package (from ip-assist-lite)
medparse-api            0.1.0   # Optional sidecar (separate repo)
```

### PDF Processing (4 packages)
```
pdfplumber              0.11.7
PyMuPDF                 1.24.9
PyMuPDFb                1.24.9
pypdfium2               4.30.0
```

### NLP/Medical (9 packages)
```
scispacy                0.5.4
en-core-sci-lg          0.5.4   # Model (installed separately)
sentence-transformers   5.1.1
spacy                   3.7.4
spacy-legacy            3.0.12
spacy-loggers           1.0.5
torch                   2.8.0
torchvision             0.23.0
transformers            4.56.2
```

### ML/Data (4 packages)
```
numpy                   1.26.4
pandas                  2.3.2
scikit-learn            1.7.2
scipy                   1.10.1
```

### API/Web (6 packages)
```
fastapi                 0.115.0
httpx                   0.27.2
pydantic                2.8.2
pydantic_core           2.20.1
pydantic-settings       2.4.0
uvicorn                 0.30.6
```

### CLI (3 packages)
```
click                   8.3.0
rich                    14.1.0
typer                   0.9.4
```

### Development (2 packages)
```
pytest                  8.4.2
pytest-cov              7.0.0
```

---

## 🚨 Common Pitfalls & Solutions

### Issue 1: "No module named 'medparse'"
**Cause**: Not in correct environment or package not installed
**Fix**:
```bash
conda activate medparse-py311
pip install -e .
```

### Issue 2: "Can't find model 'en_core_sci_lg'"
**Cause**: scispaCy model not installed
**Fix**:
```bash
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz
```

### Issue 3: sklearn version warnings
**Cause**: Classifier trained on sklearn 1.1.2, running on 1.7.2
**Impact**: Non-fatal, graceful fallback to rules
**Fix** (Optional - Patch 9): Retrain classifier on current sklearn version

### Issue 4: Package 'e' found in environment
**Cause**: Typo `pip install e .` instead of `pip install -e .`
**Fix**:
```bash
pip uninstall -y e
pip install -e .
```

### Issue 5: Binary wheel build failures
**Cause**: Trying to install sklearn/scipy from source
**Fix**: Use pinned versions with binary wheels:
```bash
pip install "scikit-learn>=1.3,<1.8" "scipy<1.11"
```

---

## 🎯 Quick Reference

### Verify Environment
```bash
python scripts/dev/preflight.py
```

### Check medparse Import Path
```bash
python -c "import medparse; print(medparse.__file__)"
# Expected: /home/rjm/projects/IP_assist_lite/medparse/__init__.py
```

### List Installed Packages
```bash
pip list | grep -E "medparse|spacy|scikit|pydantic"
```

### Run Extraction
```bash
# Direct Python (recommended)
python scripts/batch_extract_all.py

# CLI (has known issues, use scripts instead)
python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache
```

---

## 📚 Further Reading

- [CLAUDE.md](CLAUDE.md) - Project instructions and architecture
- [HANDOFF_NEXT_SESSION.md](HANDOFF_NEXT_SESSION.md) - Next steps and pending tasks
- [IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md) - Completed patches
- [UPDATED_WORKFLOW.md](UPDATED_WORKFLOW.md) - Environment setup workflow
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Common operations cheat sheet

---

*Generated: 2025-10-28 | Environment: medparse-py311 | Python: 3.11.13*
