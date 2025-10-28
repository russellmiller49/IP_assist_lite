#!/bin/bash
# Install QuickUMLS (optional UMLS linking tool)

set -e

ENV_NAME="medparse-py311"

echo "=== Installing QuickUMLS in $ENV_NAME ==="

# Install QuickUMLS from PyPI
echo "Installing QuickUMLS..."
conda run -n $ENV_NAME pip install quickumls

# Verify installation
echo ""
echo "Verifying installation..."
conda run -n $ENV_NAME python - <<'PY'
try:
    from quickumls import QuickUMLS
    print("✓ QuickUMLS installed successfully")
    print("")
    print("Next steps:")
    print("1. Download UMLS data (you'll need a UMLS license)")
    print("2. Build the QuickUMLS index:")
    print("   python -m quickumls.install /path/to/umls/data /path/to/output")
    print("")
    print("For more info: https://github.com/Georgetown-IR-Lab/QuickUMLS")
except ImportError as e:
    print(f"✗ QuickUMLS installation failed: {e}")
PY

