#!/bin/bash
# Quick fix for ipassist-py311 - avoids compilation errors

set -e

echo "=== Quick Fix for ipassist-py311 ==="

# Remove empty environment if it exists
conda env remove -n ipassist-py311 -y 2>/dev/null || true

# Create fresh environment
echo "Creating ipassist-py311..."
conda create -n ipassist-py311 python=3.11 -y

# Activate and install packages (avoiding problematic versions)
conda activate ipassist-py311

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install PyTorch (CPU version for simplicity)
echo "Installing PyTorch..."
pip install "torch==2.9.0" "torchvision" "torchaudio"

# PDF engines
echo "Installing PDF engines..."
pip install "PyMuPDF==1.24.9" "pdfplumber==0.11.7"

# NLP stack
echo "Installing NLP stack..."
pip install "spacy==3.7.4" "scispacy==0.5.4"

# Use sklearn with pre-built wheels (1.3.2 has wheels, avoids compilation)
echo "Installing sklearn (using version with pre-built wheels)..."
pip install "scikit-learn==1.3.2" "joblib>=1.3"

# Vector search and utilities
echo "Installing utilities..."
pip install "nmslib==2.1.2" "typer>=0.12,<1.0" "tqdm" "rich" "pandas>=2.0" "numpy>=1.26"

# Install IP Assist Lite
echo "Installing IP Assist Lite..."
cd /home/rjm/projects/IP_assist_lite
pip install -e .

# Verify installation
echo ""
echo "=== Verification ==="
python - <<'PY'
try:
    import medparse
    print("✓ medparse available")
except Exception as e:
    print(f"✗ medparse: {e}")

try:
    import spacy
    print(f"✓ spacy: {spacy.__version__}")
except Exception as e:
    print(f"✗ spacy: {e}")

try:
    import sklearn
    print(f"✓ sklearn: {sklearn.__version__}")
except Exception as e:
    print(f"✗ sklearn: {e}")

try:
    import torch
    print(f"✓ torch: {torch.__version__}")
except Exception as e:
    print(f"✗ torch: {e}")
PY

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Note: en_core_sci_lg model is optional (for UMLS enrichment)"
echo "If you need it later, we'll find an alternative installation method"
echo ""
echo "To activate: conda activate ipassist-py311"
echo "To verify: python scripts/doctor.py"

