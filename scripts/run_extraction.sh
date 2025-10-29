#!/bin/bash
# Script to run medparse extraction with proper environment

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Use conda run to ensure proper environment
echo "Running extraction with medparse-py311 environment..."

conda run -n medparse-py311 python -m medparse.cli extract-articles \
    "data/Input pdfs/articles/pdf" \
    --out out/articles \
    --config configs/run_article.yaml \
    --profile enriched \
    --no-cache \
    "$@"