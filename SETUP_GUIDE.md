# IP Assist Lite - Setup Guide

Complete guide for setting up the IP Assist Lite environment.

## Environment Configuration

### Current Setup

**Environment:** `medparse-py311`

This environment contains:
- ✅ medparse (v0.1.0)
- ✅ spaCy 3.7.4 with en_core_sci_lg model
- ✅ scikit-learn 1.7.2
- ✅ FastAPI, Typer, PyMuPDF, pdfplumber
- ✅ QuickUMLS (optional)
- ✅ All dependencies

### Environment Variables

The `.env` file contains:
```bash
UMLS_API_KEY=360eb22b-f8c7-4c91-b581-630a3dd068f9
QUICKUMLS_PATH=/home/rjm/quickumls_data
```

These are loaded automatically by the extraction scripts.

### Loading Environment Variables

#### Method 1: Manual (Current Shell)

```bash
set -a
source <(grep -v '^#' .env | grep -v '^$' | sed 's/#.*$//g' | grep '=')
set +a
```

#### Method 2: Using Helper Script

```bash
source scripts/load_env.sh
```

#### Method 3: Direct Export (for single session)

```bash
export UMLS_API_KEY=$(grep UMLS_API_KEY .env | cut -d '=' -f2)
export QUICKUMLS_PATH=$(grep QUICKUMLS_PATH .env | cut -d '=' -f2)
```

## Verification

Test that everything is configured:

```bash
# Activate environment
conda activate medparse-py311

# Load environment variables
source scripts/load_env.sh

# Verify
python - << 'PY'
import os
print("UMLS_API_KEY:", os.getenv('UMLS_API_KEY', 'NOT SET')[:20] + '...')
print("QUICKUMLS_PATH:", os.getenv('QUICKUMLS_PATH', 'NOT SET'))
import medparse, spacy
print("✓ medparse imported")
nlp = spacy.load('en_core_sci_lg')
print("✓ spaCy model loaded")
PY
```

## Installation

Already completed! The environment is ready to use.

If you need to recreate:
1. `conda activate medparse-py311`
2. Packages are already installed
3. Environment variables are in `.env`

## Troubleshooting

### Import Errors

```bash
# Reinstall in editable mode
cd /home/rjm/projects/IP_assist_lite
conda activate medparse-py311
pip install -e .
```

### Environment Variables Not Loading

Check `.env` file exists:
```bash
ls -la .env
cat .env | grep UMLS
```

### CLI Not Working

Verify you're in the right directory and environment:
```bash
conda activate medparse-py311
which python
python -m medparse.cli --help
```

## Next Steps

- Run batch extractions: See `BATCH_EXTRACTION.md`
- Quick start: See `QUICK_START.md`
- Full documentation: See `docs/` and `documentation/`

