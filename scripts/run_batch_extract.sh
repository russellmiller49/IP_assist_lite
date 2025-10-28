#!/bin/bash
# Run batch extraction scripts with environment variables loaded

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load environment variables
echo "Loading environment variables..."
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a  # automatically export all variables
    source <(grep -v '^#' "$PROJECT_ROOT/.env" | grep -v '^$' | sed 's/#.*$//g' | grep '=')
    set +a
    echo "✓ Environment variables loaded"
else
    echo "⚠ No .env file found"
fi

# Activate environment
echo "Activating medparse-py311..."
eval "$(conda shell.bash hook)"
conda activate medparse-py311 || echo "⚠ Failed to activate conda environment"

# Verify environment
echo ""
echo "=== Environment Variables ==="
if [ -n "$UMLS_API_KEY" ]; then
    echo "✓ UMLS_API_KEY: ${UMLS_API_KEY:0:20}..."
else
    echo "✗ UMLS_API_KEY not set"
fi

if [ -n "$QUICKUMLS_PATH" ]; then
    echo "✓ QUICKUMLS_PATH: $QUICKUMLS_PATH"
    if [ -d "$QUICKUMLS_PATH" ]; then
        echo "  ✓ Directory exists"
    else
        echo "  ⚠ Directory does not exist (will be created when needed)"
    fi
else
    echo "✗ QUICKUMLS_PATH not set"
fi

echo ""
echo "=== Running Extraction Commands ==="
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Run Articles extraction
echo "--- Extracting Articles ---"
python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf" --out out/articles --config configs/run_article.yaml --profile enriched --no-cache
echo ""

# Run IFUs extraction
echo "--- Extracting IFUs ---"
python -m medparse.cli extract-ifus "data/Input pdfs/IFUs/pdf" --out out/ifus --config configs/run_ifu.yaml --profile enriched --no-cache
echo ""

# Run Textbooks extraction
echo "--- Extracting Textbooks ---"
python -m medparse.cli extract-textbook "data/Input pdfs/Texbooks" --out out/textbooks --config configs/run_textbook.yaml --profile enriched --no-cache
echo ""

echo "=== Batch extraction complete ==="

