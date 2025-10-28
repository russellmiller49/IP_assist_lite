#!/bin/bash
# Setup script for the three Python 3.11 environments
# Run this script to create and configure all three environments

set -e  # Exit on error

# Initialize conda
CONDA_BASE=$(conda info --base)
source "$CONDA_BASE/etc/profile.d/conda.sh"

echo "=== Setting up IP Assist Lite environments ==="

# Section 1: Hard reset any conflicting installs
echo ""
echo "Section 1: Cleaning up any conflicting installations..."
read -p "Do you want to clean up existing environments first? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstalling medparse packages from current environment..."
    python -m pip uninstall -y medparse ip-assist-lite medparse-api 2>/dev/null || true
    python -m pip cache purge 2>/dev/null || true
fi

# Section 2: Create environments
echo ""
echo "=== Section 2: Creating environments ==="

# 2.1 ipassist-py311
echo ""
echo "Creating ipassist-py311 environment..."
conda create -n ipassist-py311 python=3.11 -y
conda activate ipassist-py311

python -m pip install --upgrade pip setuptools wheel

# Core pins
pip install "torch==2.9.0"
pip install "PyMuPDF==1.24.9" "pdfplumber==0.11.7"

# NLP stack
pip install "spacy==3.7.4" "scispacy==0.5.4"

# Install scispaCy model (DO NOT use spacy download)
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz

# Vector search, CLI, data
pip install "nmslib==2.1.2" "typer>=0.12,<1.0" "tqdm" "rich" "pandas>=2.0" "numpy>=1.26"

# scikit-learn: Using 1.1.2 to avoid pickle warnings
pip install "scikit-learn==1.1.2" "joblib>=1.3"

# Install the runner from repo root
echo "Installing ip-assist-lite from repo root..."
cd /home/rjm/projects/IP_assist_lite
pip install -e .

# Verify installation
python - <<'PY'
import medparse, inspect
print("✓ medparse file:", inspect.getsourcefile(medparse) or medparse.__file__)

import spacy
nlp = spacy.load("en_core_sci_lg")
print("✓ spaCy model loaded:", nlp.meta.get("name"), nlp.meta.get("version"))

import sklearn
print("✓ sklearn version:", sklearn.__version__)
PY

echo ""
echo "✓ ipassist-py311 environment created successfully"
conda deactivate

# 2.2 medparse-lib-py311
echo ""
echo "Creating medparse-lib-py311 environment..."
conda create -n medparse-lib-py311 python=3.11 -y
conda activate medparse-lib-py311 2>/dev/null || eval "$(conda shell.bash hook)" && conda activate medparse-lib-py311

python -m pip install --upgrade pip setuptools wheel
pip install "PyMuPDF==1.24.9" "pdfplumber==0.11.7"
pip install "spacy==3.7.4" "scispacy==0.5.4"
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz
pip install "nmslib==2.1.2" "typer>=0.12,<1.0" "tqdm" "rich" "pandas>=2.0" "numpy>=1.26"
pip install "scikit-learn==1.1.2" "joblib>=1.3"
pip install "pytest" "pytest-cov" "hypothesis"

# Install from medparse repo
if [ -d "/home/rjm/projects/ip_knowledge/medparse/medparse-docling" ]; then
    cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
    pip install -e .
    echo "✓ medparse-lib-py311 environment created successfully"
else
    echo "⚠ Medparse repo not found at /home/rjm/projects/ip_knowledge/medparse/medparse-docling"
fi

conda deactivate

# 2.3 medparse-api-py311
echo ""
echo "Creating medparse-api-py311 environment..."
conda create -n medparse-api-py311 python=3.11 -y
conda activate medparse-api-py311 2>/dev/null || eval "$(conda shell.bash hook)" && conda activate medparse-api-py311

python -m pip install --upgrade pip setuptools wheel
pip install "fastapi==0.115.0" "uvicorn[standard]==0.30.6" "pydantic==2.8.2" "pydantic-settings==2.4.0" "orjson==3.10.7" "loguru==0.7.2" "httpx==0.27.2"

# Install from medparse repo
if [ -d "/home/rjm/projects/ip_knowledge/medparse/medparse-docling" ]; then
    cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
    pip install -e .
    echo "✓ medparse-api-py311 environment created successfully"
else
    echo "⚠ Medparse repo not found at /home/rjm/projects/ip_knowledge/medparse/medparse-docling"
fi

conda deactivate

echo ""
echo "=== Environment setup complete ==="
echo ""
echo "Available environments:"
echo "  1. ipassist-py311          - for IP_assist_lite CLI (extractors, pipeline, batch, tests)"
echo "  2. medparse-lib-py311       - for Medparse library repo (optional)"
echo "  3. medparse-api-py311       - for FastAPI service"
echo ""
echo "To activate an environment, run:"
echo "  conda activate ipassist-py311"
echo ""

