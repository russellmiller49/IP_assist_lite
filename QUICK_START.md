# IP Assist Lite - Quick Start Guide

Medical Information Retrieval for Interventional Pulmonology

## Prerequisites

- Python 3.11
- Conda
- Git

## Environment Setup

### 1. Create and Activate Environment

```bash
conda activate medparse-py311
```

This environment already has everything installed.

### 2. Load Environment Variables

```bash
cd /home/rjm/projects/IP_assist_lite

# Load environment variables
set -a
source <(grep -v '^#' .env | grep -v '^$' | sed 's/#.*$//g' | grep '=')
set +a
```

Or use the helper script:
```bash
bash scripts/load_env.sh
```

### 3. Verify Setup

```bash
# Check environment variables
echo $UMLS_API_KEY
echo $QUICKUMLS_PATH

# Test imports
python -c "import medparse, spacy; print('✓ Ready')"
```

## Quick Usage

### Run Batch Extractions

```bash
./run_extractions.sh
```

This extracts:
- Articles (guidelines + research)
- IFUs (Instruction for Use)
- Textbooks

### Individual Commands

```bash
# Articles
python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache \
  --second-pass auto \
  --chunking smart \
  --evidence-policy compact \
  --tables-mode compact

# IFUs
python -m medparse.cli extract-ifus "data/Input pdfs/IFUs/pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched \
  --no-cache \
  --second-pass auto \
  --chunking smart \
  --evidence-policy compact \
  --tables-mode compact \
  --ifu-engine hybrid \
  --ifu-fast-long-docs

# Textbooks
python -m medparse.cli extract-textbook "data/Input pdfs/Texbooks" \
  --out out/textbooks \
  --config configs/run_textbook.yaml \
  --profile enriched \
  --no-cache
```

## Output Locations

Results are saved to:
- `out/articles/` - Article extractions
- `out/ifus/` - IFU extractions
- `out/textbooks/` - Textbook extractions

`configs/run_ifu.yaml` defines manufacturer overrides and engine selection. CLI flags such as `--ifu-engine` (`pymupdf`, `pdfplumber`, or `hybrid`) and `--ifu-fast-long-docs/--no-ifu-fast-long-docs` can override the YAML defaults. Long manuals stream in 40-page windows (`ifu.extract.long_doc.pages_per_batch`) with a 10 s per-page timeout guard; `_metrics.streaming_fallback` records `windows_completed`, `last_completed_page`, and any `batches_failed` so you can confirm streaming health during QA.

## Smart Chunking

Articles and IFUs now emit `chunks[]`—layout-aware windows (≈200–500 tokens) keyed by paragraph hashes for downstream retrieval. Chunking is enabled by default via `configs/_shared/emit.yaml` and can be toggled per run with `--chunking smart|off`. Metrics surface under `_metrics.chunking` (enabled flag, chunk count, average tokens, overlap ratio) so QA can verify coverage.

## Configuration

Environment variables in `.env`:
- `UMLS_API_KEY` - For concept linking
- `QUICKUMLS_PATH` - Path to QuickUMLS database (optional)

Key IFU configuration files:
- `configs/_shared/ifu_frontmatter.yaml` – regex `pattern_bundle` for manufacturer, product name, part number, revision, publication date, and model. Extend this file when onboarding a new vendor.
- `configs/_shared/second_pass.yaml` – houses second-pass defaults, including the unified safety density thresholds: ≤4 pages ⇒ ≥8 blocks, ≥40 pages ⇒ ≥20 blocks, else ≥12. The booster writes `_metrics.safety_blocks_added`, and the validator only warns when the final count remains below the target after boosting.
- `configs/run_ifu.yaml` – controls TOC guard, streaming knobs (`ifu.extract.long_doc.*`), chunking defaults, and the tables cap (`emit.max_tables` / `size_guards.max_tables`, now 24).
- `text_normalization.enabled` (set in both `configs/run_article.yaml` and `configs/run_ifu.yaml`) keeps ingestion fixes on by default—fraction ligatures, unit spacing, and run-on repairs record a `_normalization.report` in `_metrics`.
- `tables.sterilization_hints.enabled` (per config) toggles IFU-only sterilization table detection. Disable it if a PDF set has incompatible scans.

Each extraction now records a second-pass summary (`second_pass.applied`, `second_pass.reasons`) plus a per-patch array (`_metrics.patches[]` with `name`, `modifications`, and `reasons`). Table budgets and counts are mirrored (`_metrics.tables_original|kept|dropped`) so you can verify that streaming flushes preserved tables and that no rows were dropped unexpectedly.

Article payloads now expose richer structured fields by default:
- `abstract` captures both free-form text and, when headings exist, a structured map (background/methods/results/conclusions) so downstream summarizers can target the right subsection.
- `keywords[]` and `clinical_trials[]` (with `registry` + `id`, e.g., `NCT` numbers) surface front-matter metadata even when PDFs bury it in sidebars.
- `statistical_results[]` enumerates comparisons parsed from research text (_e.g._ VERITAS and VENT trials), including per-arm values, confidence intervals, p-values, and `evidence_refs` for easy traceability.

## Troubleshooting

### Command prints "medparse 1.1.0" and exits

Load environment variables first:
```bash
source scripts/load_env.sh
```

### Import errors

Verify you're using the correct environment:
```bash
conda activate medparse-py311
which python
```

### Environment variables not set

Ensure `.env` file exists and has the required variables.

## For More Help

- Detailed setup: `SETUP_SUMMARY.md`
- Batch extraction: `BATCH_EXTRACTION.md`
- Full docs: `docs/` and `documentation/` folders
