#!/bin/bash
# Manual setup script - creates environments one at a time
# This avoids conda initialization issues by using explicit paths

set -e

echo "=== IP Assist Lite Environment Setup (Manual) ==="
echo ""
echo "This script will create three Python 3.11 environments."
echo ""

# Find conda
if command -v conda &> /dev/null; then
    CONDA_BASE=$(conda info --base 2>/dev/null || echo "")
    if [ -z "$CONDA_BASE" ]; then
        echo "Error: Cannot find conda base directory"
        exit 1
    fi
    echo "Using conda at: $CONDA_BASE"
else
    echo "Error: conda command not found"
    exit 1
fi

# Environment 1: ipassist-py311
echo ""
echo "=== 1/3: Creating ipassist-py311 environment ==="
conda create -n ipassist-py311 python=3.11 -y

# Create activation script for this environment
cat > /tmp/setup_ipassist.sh << 'EOF'
#!/bin/bash
conda run -n ipassist-py311 --live-stream python -m pip install --upgrade pip setuptools wheel
conda run -n ipassist-py311 --live-stream pip install "torch==2.9.0"
conda run -n ipassist-py311 --live-stream pip install "PyMuPDF==1.24.9" "pdfplumber==0.11.7"
conda run -n ipassist-py311 --live-stream pip install "spacy==3.7.4" "scispacy==0.5.4"
conda run -n ipassist-py311 --live-stream pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz
conda run -n ipassist-py311 --live-stream pip install "nmslib==2.1.2" "typer>=0.12,<1.0" "tqdm" "rich" "pandas>=2.0" "numpy>=1.26"
conda run -n ipassist-py311 --live-stream pip install "scikit-learn==1.1.2" "joblib>=1.3"
cd /home/rjm/projects/IP_assist_lite
conda run -n ipassist-py311 --live-stream pip install -e .
EOF

chmod +x /tmp/setup_ipassist.sh
bash /tmp/setup_ipassist.sh

echo "✓ ipassist-py311 created"

# Environment 2: medparse-lib-py311 (optional)
echo ""
echo "=== 2/3: Creating medparse-lib-py311 environment (optional) ==="
read -p "Create medparse-lib-py311? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    conda create -n medparse-lib-py311 python=3.11 -y
    
    cat > /tmp/setup_medparse_lib.sh << 'EOF'
#!/bin/bash
conda run -n medparse-lib-py311 --live-stream python -m pip install --upgrade pip setuptools wheel
conda run -n medparse-lib-py311 --live-stream pip install "PyMuPDF==1.24.9" "pdfplumber==0.11.7"
conda run -n medparse-lib-py311 --live-stream pip install "spacy==3.7.4" "scispacy==0.5.4"
conda run -n medparse-lib-py311 --live-stream pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz
conda run -n medparse-lib-py311 --live-stream pip install "nmslib==2.1.2" "typer>=0.12,<1.0" "tqdm" "rich" "pandas>=2.0" "numpy>=1.26"
conda run -n medparse-lib-py311 --live-stream pip install "scikit-learn==1.1.2" "joblib>=1.3"
conda run -n medparse-lib-py311 --live-stream pip install "pytest" "pytest-cov" "hypothesis"
if [ -d "/home/rjm/projects/ip_knowledge/medparse/medparse-docling" ]; then
    cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
    conda run -n medparse-lib-py311 --live-stream pip install -e .
fi
EOF
    
    chmod +x /tmp/setup_medparse_lib.sh
    bash /tmp/setup_medparse_lib.sh
    echo "✓ medparse-lib-py311 created"
else
    echo "Skipping medparse-lib-py311"
fi

# Environment 3: medparse-api-py311
echo ""
echo "=== 3/3: Creating medparse-api-py311 environment ==="
read -p "Create medparse-api-py311? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    conda create -n medparse-api-py311 python=3.11 -y
    
    cat > /tmp/setup_medparse_api.sh << 'EOF'
#!/bin/bash
conda run -n medparse-api-py311 --live-stream python -m pip install --upgrade pip setuptools wheel
conda run -n medparse-api-py311 --live-stream pip install "fastapi==0.115.0" "uvicorn[standard]==0.30.6" "pydantic==2.8.2" "pydantic-settings==2.4.0" "orjson==3.10.7" "loguru==0.7.2" "httpx==0.27.2"
if [ -d "/home/rjm/projects/ip_knowledge/medparse/medparse-docling" ]; then
    cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
    conda run -n medparse-api-py311 --live-stream pip install -e .
fi
EOF
    
    chmod +x /tmp/setup_medparse_api.sh
    bash /tmp/setup_medparse_api.sh
    echo "✓ medparse-api-py311 created"
else
    echo "Skipping medparse-api-py311"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To activate ipassist-py311:"
echo "  conda activate ipassist-py311"
echo ""
echo "If conda activate doesn't work, run this first:"
echo "  eval \"\$(conda shell.bash hook)\""
echo "  conda activate ipassist-py311"
echo ""
echo "Then verify with:"
echo "  python scripts/doctor.py"

