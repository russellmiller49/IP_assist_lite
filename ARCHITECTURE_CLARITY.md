# Architecture: How medparse (library) and IP_assist_lite (runner) Work Together

## Repository Structure

```
IP_assist_lite/
├── medparse/                    # LIBRARY: Core extraction engine
│   ├── schema/                  # Pydantic models (Article, IFU, Textbook, etc.)
│   ├── extractors/              # Document-type specific extraction logic
│   ├── normalize/               # Post-processing (UMLS, relations, grading, etc.)
│   ├── validate/                # Quality gates and validators
│   ├── pipeline/                # Orchestration (run_extract, engines, OCR fallback)
│   ├── classify/                # Document type classification
│   ├── config.py                # ExtractionConfig, ExtractionProfile
│   └── cli.py                   # Basic CLI entry points
│
├── configs/                     # RUNNER: Configuration files (AUTHORITATIVE)
│   ├── run_article.yaml         # Article extraction settings
│   ├── run_ifu.yaml             # IFU extraction settings
│   ├── run_textbook.yaml        # Textbook extraction settings
│   └── chunking.yaml            # (for downstream RAG chunking)
│
├── src/                         # RUNNER: Orchestration, RAG, UI
│   ├── index/                   # Chunking, embedding, Qdrant indexing
│   ├── retrieval/               # Hybrid search, MedCPT
│   ├── graph/                   # Neo4j integration
│   ├── api/                     # FastAPI endpoints
│   └── eval/                    # Evaluation and metrics
│
├── scripts/                     # RUNNER: Batch jobs, utilities, CI
│   └── dev/                     # Development tools (preflight.py)
│
├── app.py                       # RUNNER: Gradio UI
├── Makefile                     # RUNNER: Build targets, CI commands
└── pyproject.toml               # Package definition (ip-assist-lite + medparse)
```

## Division of Responsibilities

### medparse/ (Library) - "The Engine"

**Owns:**
- ✅ **Schemas**: `Article`, `IFU`, `Textbook`, `Guideline`, `Reference`, `Evidence`
- ✅ **Extractors**: `ArticleExtractor`, `IFUExtractor`, `TextbookExtractor`
- ✅ **Normalizers**: `link_umls_entities`, `extract_relations`, `normalize_guideline_grades`, `classify_tables`
- ✅ **Validators**: `ArticleValidator`, `IFUValidator`, contract checks
- ✅ **Pipeline**: `run_extract()` orchestrator, engine fallback logic, OCR retry
- ✅ **Profiles**: `ExtractionProfile.ENRICHED`, `ExtractionProfile.FAST_RAW`
- ✅ **Config**: `ExtractionConfig` (runtime settings, toggles)

**Does NOT own:**
- ❌ Concrete YAML configs (those live in `configs/`)
- ❌ RAG indexing/chunking (that's `src/index/`)
- ❌ UI/API (that's `app.py`, `src/api/`)
- ❌ CI orchestration (that's `Makefile`, `scripts/`)

**Key Principle**: The library is **policy-driven** but **config-agnostic**. It knows *how* to extract, but the *what* (thresholds, toggles, emit format) comes from configs.

---

### configs/ (Runner) - "The Controller"

**Owns:**
- ✅ **Extraction configs**: `run_article.yaml`, `run_ifu.yaml`, `run_textbook.yaml`
- ✅ **Threshold tuning**: Quality gates, min_chars, min_pages_ratio
- ✅ **Emit settings**: `include_page_text`, `max_evidence_chars`, `dedupe_evidence`
- ✅ **Feature toggles**: `enable_umls`, `enable_relations`, `enable_validators`
- ✅ **Domain-specific tuning**: Half-lives, recency weights, section priorities

**Authoritative for CI**: Tests run with `--profile enriched` and verify output against these configs.

**Example** (`configs/run_article.yaml`):
```yaml
profile: enriched
emit:
  include_page_text: false       # Size reduction
  max_evidence_chars: 2000       # Cap per evidence blob
  dedupe_evidence: true          # Hash and reuse
  keep_tables_raw: false         # Normalized only
thresholds:
  min_chars: 20000
  min_pages_ratio: 0.95
enable_umls: true
enable_relations: true
```

---

### src/ (Runner) - "The Downstream Pipeline"

**Owns:**
- ✅ **Chunking**: Variable-length, section-aware (uses medparse output)
- ✅ **Embedding**: MedCPT, batch processing, GPU optimization
- ✅ **Indexing**: Qdrant upsert, term indexes (CPT, aliases)
- ✅ **Retrieval**: Hybrid search, hierarchy-aware ranking
- ✅ **Graph**: Neo4j backfill, relation storage
- ✅ **API**: FastAPI endpoints wrapping extraction + retrieval

**Consumes**: JSON output from `medparse.pipeline.run_extract()`

---

### Makefile + scripts/ (Runner) - "The Orchestrator"

**Owns:**
- ✅ **CI targets**: `make setup`, `make test`, `make preflight`
- ✅ **Batch processing**: `make batch INPUT=... OUTPUT=...`
- ✅ **Pipeline orchestration**: `make all` (prep → chunk → embed → index)
- ✅ **Environment management**: `make setup-enriched`, conda setup
- ✅ **Quality gates**: Run validators, emit reports

---

## How They Work Together

### Example: Extracting an Article

1. **Runner invokes CLI** (from `medparse.cli`):
   ```bash
   python -m medparse.cli extract-articles "input.pdf" \
     --out out/ \
     --config configs/run_article.yaml \
     --profile enriched
   ```

2. **medparse.pipeline.run_extract()** orchestrates:
   - Load `configs/run_article.yaml` → `ExtractionConfig`
   - Classify document → `ArticleExtractor`
   - Extract structure (frontmatter, sections, tables, references)
   - **Normalize** (if `enable_umls=true`):
     - `link_umls_entities()` → biomedical entity linking
     - `extract_relations()` → outcome→intervention pairs
     - `normalize_guideline_grades()` → parse ATS/GRADE
   - **Validate** (if `enable_validators=true`):
     - `ArticleValidator.validate()` → contract checks
   - **Emit** JSON (respecting `emit.max_evidence_chars`, `dedupe_evidence`)

3. **Runner indexes output** (optional, for RAG):
   ```bash
   make ingest-json JSON="out/articles/*.json"
   # → chunks → embeddings → Qdrant
   ```

4. **CI verifies**:
   ```bash
   pytest tests/integration/test_article_extraction.py \
     --profile enriched \
     --config configs/run_article.yaml
   # Asserts output matches schema, validators pass, no regressions
   ```

---

## Patches Applied Today (Branch: infra/env-guards-and-profile-sanity)

### Finished in medparse/ (Library)

✅ **Patch 1**: `medparse/normalize/umls_linking.py`
- Model fallback: `en_core_sci_lg → md → sm`
- Graceful degradation if no models available

✅ **Patch 2**: `pyproject.toml`
- Pin compatible ranges (sklearn, typer, scipy)
- Add `[enriched]` optional dependencies

✅ **Patch 5**: `medparse/classify/model.py`
- Version-safe unpickling for sklearn models

### Finished in Runner

✅ **Patch 3**: `scripts/dev/preflight.py` + `README.md`
- Environment validation script
- Setup documentation

✅ **Patch 4**: `Makefile`
- `setup-enriched` target
- Safety checks (uninstall `e` package)

### Still TODO (from IMPLEMENTATION_SUMMARY.md)

#### C) Document Type Classifier Retraining
**Owner**: Runner (`scripts/train_doc_type.py`)
- Train on sklearn 1.7.2 to eliminate version warnings
- Output versioned bundle: `models/doc_type_bundle.joblib`
- Library loads bundle via `medparse/classify/model.py`

#### D) JSON Output Size Caps
**Owner**: Configs (`configs/run_*.yaml`)
- Add to all config files:
  ```yaml
  emit:
    include_page_text: false
    max_evidence_chars: 2000
    dedupe_evidence: true
    keep_tables_raw: false
  tables:
    max_cells: 1000
  ```
- **Optional**: Implement evidence store in `medparse/schema/` for deduplication

---

## Key Takeaway

> **configs/ is authoritative for CI and production runs.**
>
> medparse/ implements the *how*, configs/ defines the *what*.
>
> CI tests run `--profile enriched` with config files to ensure contract compliance.

Your understanding is **100% correct**!

Does this clarify the separation? Should we proceed with C (classifier training) or D (output caps)?
