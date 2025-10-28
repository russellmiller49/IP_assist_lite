# Environment Setup Guide

This guide helps you create and manage three separate Python 3.11 environments for IP Assist Lite.

## Overview

Three separate Python 3.11 environments:

1. **ipassist-py311** – runs the IP_assist_lite CLI (extractors, pipeline, batch, tests).
2. **medparse-lib-py311** – for the Medparse library repo (optional).
3. **medparse-api-py311** – for the FastAPI service.

Why three? It prevents version pin fights (e.g., Typer/Gradio, scikit-learn pickle versions, spaCy model availability).

## Quick Setup

### Automated Setup

```bash
# Make the setup script executable
chmod +x scripts/setup_environments.sh

# Run the setup script
bash scripts/setup_environments.sh
```

### Manual Setup

See detailed sections below for step-by-step manual setup.

## Environment 1: ipassist-py311

For IP_assist_lite CLI operations.

```bash
# Create environment
conda create -n ipassist-py311 python=3.11 -y
conda activate ipassist-py311

# Upgrade pip
python -m pip install --upgrade pip setuptools wheel

# Install PyTorch (CPU or GPU)
pip install "torch==2.9.0"

# PDF engines + table lib
pip install "PyMuPDF==1.24.9" "pdfplumber==0.11.7"

# NLP stack
pip install "spacy==3.7.4" "scispacy==0.5.4"

# Install scispaCy model (DO NOT use spacy download)
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz

# Vector search, CLI, data
pip install "nmslib==2.1.2" "typer>=0.12,<1.0" "tqdm" "rich" "pandas>=2.0" "numpy>=1.26"

# scikit-learn: pin to 1.1.2 for pickle compatibility
pip install "scikit-learn==1.1.2" "joblib>=1.3"

# Install the runner from repo root
cd /home/rjm/projects/IP_assist_lite
pip install -e .

# Verify installation
python - <<'PY'
import medparse, inspect
print("medparse file:", inspect.getsourcefile(medparse) or medparse.__file__)

import spacy
nlp = spacy.load("en_core_sci_lg")
print("spaCy model:", nlp.meta.get("name"), nlp.meta.get("version"))
PY
```

## Environment 2: medparse-lib-py311

For Medparse library development (optional).

```bash
conda create -n medparse-lib-py311 python=3.11 -y
conda activate medparse-lib-py311

python -m pip install --upgrade pip setuptools wheel
pip install "PyMuPDF==1.24.9" "pdfplumber==0.11.7"
pip install "spacy==3.7.4" "scispacy==0.5.4"
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz
pip install "nmslib==2.1.2" "typer>=0.12,<1.0" "tqdm" "rich" "pandas>=2.0" "numpy>=1.26"
pip install "scikit-learn==1.1.2" "joblib>=1.3"
pip install "pytest" "pytest-cov" "hypothesis"

# Install from medparse repo
cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
pip install -e .
```

## Environment 3: medparse-api-py311

For FastAPI service (isolated from CLI).

```bash
conda create -n medparse-api-py311 python=3.11 -y
conda activate medparse-api-py311

python -m pip install --upgrade pip setuptools wheel
pip install "fastapi==0.115.0" "uvicorn[standard]==0.30.6" "pydantic==2.8.2" "pydantic-settings==2.4.0" "orjson==3.10.7" "loguru==0.7.2" "httpx==0.27.2"

# Install from medparse repo
cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
pip install -e .
```

## Environment Variables

Add to your shell profile for ipassist-py311:

```bash
export MEDPARSE_PROFILE=enriched
export MEDPARSE_UMLS_MODEL=en_core_sci_lg
export MEDPARSE_DISABLE_GPU=false
export PYTHONUTF8=1
```

## Using the CLI

Activate the environment and run:

```bash
conda activate ipassist-py311
cd /home/rjm/projects/IP_assist_lite

python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf" --out out/articles --profile enriched --no-cache --force-deep
```

## Health Check

Run the doctor script to verify your environment:

```bash
conda activate ipassist-py311
python scripts/doctor.py
```

## Common Issues

### Issue: "medparse 1.1.0" prints and exits

**Cause**: Wrong import path or multi-line command syntax.

**Fix**:
```bash
conda activate ipassist-py311
python -m pip uninstall -y medparse ip-assist-lite
python -m pip cache purge
cd /home/rjm/projects/IP_assist_lite
pip install -e .

python - <<'PY'
import medparse, inspect
print("using:", inspect.getsourcefile(medparse) or medparse.__file__)
PY
```

### Issue: InconsistentVersionWarning for scikit-learn

You see: "Trying to unpickle estimator from version 1.1.2 when using version 1.7.2"

**Solution**: Pin to the training version (1.1.2) or retrain your models under 1.7.2.

Option A (fastest): Keep scikit-learn==1.1.2 (already done above)

Option B (future-proof): Retrain models under scikit-learn==1.7.2. See `tools/rebuild_vectorizer.py`.

### Issue: spaCy en_core_sci_lg 404 error

**Fix**: Never use `python -m spacy download`. Always use:

```bash
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz
```

### Issue: Typer/Gradio conflict

If you need both Typer and Gradio in the same env:

```bash
pip install "typer>=0.12,<1.0"
```

For ipassist-py311, it's recommended to keep Gradio out to avoid pin fights.

## GPU Support

For CUDA 12.1:

```bash
pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.9.0
```

Verify:
```bash
python - <<'PY'
import torch
print("CUDA available:", torch.cuda.is_available())
PY
```

## Troubleshooting

### Check current environment

```bash
python - <<'PY'
import sys
print("Python:", sys.executable)
import medparse, inspect
print("medparse:", inspect.getsourcefile(medparse) or medparse.__file__)
PY
```

### Check package conflicts

```bash
pip check
```

### Freeze requirements

```bash
pip freeze > requirements.freeze.txt
```

### Clean rebuild

```bash
conda activate ipassist-py311
python -m pip uninstall -y medparse ip-assist-lite
python -m pip cache purge
cd /home/rjm/projects/IP_assist_lite
pip install -e .
```

## Next Steps

1. Run the setup script to create all three environments
2. Set environment variables in your shell profile
3. Test with: `python scripts/doctor.py`
4. Run extraction: `python -m medparse.cli extract-articles ...`

