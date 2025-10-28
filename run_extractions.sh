#!/bin/bash
# Run all batch extractions with proper environment loading
# This ensures UMLS_API_KEY and QUICKUMLS_PATH are available

set -e  # Exit on error

echo "=== IP Assist Lite Batch Extraction ==="
echo ""

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Load environment variables
echo "Loading environment variables..."
if [ -f "$PROJECT_ROOT/.env" ]; then
    # Use a more robust method to load .env
    set -a  # automatically export all variables
    source <(grep -v '^#' "$PROJECT_ROOT/.env" | grep -v '^$' | sed 's/#.*$//g' | grep '=')
    set +a
    echo "✓ Environment variables loaded"
    if [ -n "$UMLS_API_KEY" ]; then
        echo "  UMLS_API_KEY: ${UMLS_API_KEY:0:20}..."
    fi
    if [ -n "$QUICKUMLS_PATH" ]; then
        echo "  QUICKUMLS_PATH: $QUICKUMLS_PATH"
    fi
    if [ -n "$MEDPARSE_CLI_DEBUG_ARGS" ]; then
        echo "  MEDPARSE_CLI_DEBUG_ARGS: $MEDPARSE_CLI_DEBUG_ARGS"
    fi
else
    echo "⚠ No .env file found"
fi

# Activate conda environment
echo ""
echo "Activating medparse-py311 environment..."
eval "$(conda shell.bash hook)" || true
conda activate medparse-py311 || echo "⚠ Could not activate conda environment"

# Ensure the local package takes precedence
if [ -n "${PYTHONPATH}" ]; then
    export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH}"
else
    export PYTHONPATH="$PROJECT_ROOT"
fi

# Verify environment
echo ""
echo "=== Environment Verification ==="
type python
python -c "import medparse; import pathlib; print('✓ medparse imported from', pathlib.Path(medparse.__file__).resolve())" || exit 1
python -c "import medparse.cli, pathlib; print('✓ medparse.cli imported from', pathlib.Path(medparse.cli.__file__).resolve())"
echo ""

python - <<'PY'
import os
import subprocess
from pathlib import Path

project_root = Path(os.environ["PROJECT_ROOT"])

commands = [
    (
        "1/3: Extracting Articles (guidelines + research)",
        [
            "python",
            "-m",
            "medparse.cli",
            "extract-articles",
            str(project_root / "data/Input pdfs/articles/pdf"),
            "--out",
            str(project_root / "out/articles"),
            "--config",
            str(project_root / "configs/run_article.yaml"),
            "--profile",
            "enriched",
            "--no-cache",
        ],
    ),
    (
        "2/3: Extracting IFUs",
        [
            "python",
            "-m",
            "medparse.cli",
            "extract-ifus",
            str(project_root / "data/Input pdfs/IFUs/pdf"),
            "--out",
            str(project_root / "out/ifus"),
            "--config",
            str(project_root / "configs/run_ifu.yaml"),
            "--profile",
            "enriched",
            "--no-cache",
        ],
    ),
    (
        "3/3: Extracting Textbooks",
        [
            "python",
            "-m",
            "medparse.cli",
            "extract-textbook",
            str(project_root / "data/Input pdfs/Texbooks"),
            "--out",
            str(project_root / "out/textbooks"),
            "--config",
            str(project_root / "configs/run_textbook.yaml"),
            "--profile",
            "enriched",
            "--no-cache",
        ],
    ),
]

env = os.environ.copy()

for label, cmd in commands:
    print("==========================================")
    print(label)
    print("==========================================")
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        print(f"⚠ {label} exited with status {result.returncode}. See logs above.")
    print()
PY

echo "=========================================="
echo "✅ All batch extractions complete!"
echo "=========================================="
echo ""
echo "Output locations:"
echo "  Articles: out/articles/"
echo "  IFUs:     out/ifus/"
echo "  Textbooks: out/textbooks/"
echo ""
