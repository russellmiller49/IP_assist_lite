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
  --evidence-policy compact \
  --tables-mode compact

# IFUs
python -m medparse.cli extract-ifus "data/Input pdfs/IFUs/pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched \
  --no-cache \
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

`configs/run_ifu.yaml` defines manufacturer overrides and engine selection. CLI flags such as `--ifu-engine` (`pymupdf`, `pdfplumber`, or `hybrid`) and `--ifu-fast-long-docs/--no-ifu-fast-long-docs` can override the YAML defaults.

## Configuration

Environment variables in `.env`:
- `UMLS_API_KEY` - For concept linking
- `QUICKUMLS_PATH` - Path to QuickUMLS database (optional)

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
