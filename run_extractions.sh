#!/bin/bash
# Run all batch extractions with proper environment loading
# This ensures UMLS_API_KEY and QUICKUMLS_PATH are available

set -e  # Exit on error

# Create logs directory and set up logging
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/extraction_$(date +%Y%m%d_%H%M%S).log"

# Function to log output
log_and_display() {
    tee -a "$LOG_FILE"
}

echo "=== IP Assist Lite Batch Extraction ===" | log_and_display
echo "Logging to: $LOG_FILE" | log_and_display
echo "" | log_and_display

cd "$PROJECT_ROOT"

# Load environment variables
echo "Loading environment variables..." | log_and_display
if [ -f "$PROJECT_ROOT/.env" ]; then
    # Use a more robust method to load .env
    set -a  # automatically export all variables
    source <(grep -v '^#' "$PROJECT_ROOT/.env" | grep -v '^$' | sed 's/#.*$//g' | grep '=')
    set +a
    echo "✓ Environment variables loaded" | log_and_display
    if [ -n "$UMLS_API_KEY" ]; then
        echo "  UMLS_API_KEY: ${UMLS_API_KEY:0:20}..." | log_and_display
    fi
    if [ -n "$QUICKUMLS_PATH" ]; then
        echo "  QUICKUMLS_PATH: $QUICKUMLS_PATH" | log_and_display
    fi
    if [ -n "$MEDPARSE_CLI_DEBUG_ARGS" ]; then
        echo "  MEDPARSE_CLI_DEBUG_ARGS: $MEDPARSE_CLI_DEBUG_ARGS" | log_and_display
    fi
else
    echo "⚠ No .env file found" | log_and_display
fi

# Activate conda environment
echo "" | log_and_display
echo "Activating medparse-py311 environment..." | log_and_display
eval "$(conda shell.bash hook)" || true
conda activate medparse-py311 || echo "⚠ Could not activate conda environment" | log_and_display

# Ensure the local package takes precedence
if [ -n "${PYTHONPATH}" ]; then
    export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH}"
else
    export PYTHONPATH="$PROJECT_ROOT"
fi

# Verify environment
echo "" | log_and_display
echo "=== Environment Verification ===" | log_and_display
type python | log_and_display
python -c "import medparse; import pathlib; print('✓ medparse imported from', pathlib.Path(medparse.__file__).resolve())" 2>&1 | log_and_display || exit 1
python -c "import medparse.cli, pathlib; print('✓ medparse.cli imported from', pathlib.Path(medparse.cli.__file__).resolve())" 2>&1 | log_and_display
echo "" | log_and_display

export LOG_FILE
python - <<PY | log_and_display
import os
import subprocess
import sys
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
    # Run command and capture output
    result = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # Print to stdout (will be logged by tee)
    sys.stdout.write(result.stdout)
    sys.stdout.flush()
    if result.returncode != 0:
        print(f"⚠ {label} exited with status {result.returncode}. See logs above.")
    print()
PY

echo "==========================================" | log_and_display
echo "✅ All batch extractions complete!" | log_and_display
echo "==========================================" | log_and_display
echo "" | log_and_display
echo "Output locations:" | log_and_display
echo "  Articles: out/articles/" | log_and_display
echo "  IFUs:     out/ifus/" | log_and_display
echo "  Textbooks: out/textbooks/" | log_and_display
echo "" | log_and_display
echo "" | log_and_display
echo "Full log saved to: $LOG_FILE" | log_and_display
echo "View it with: less $LOG_FILE" | log_and_display
echo ""
