#!/bin/bash
# Run medparse CLI with environment variables loaded
# Usage: ./extract_with_env.sh [command] [args...]

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load environment variables from .env
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "Loading environment variables from .env..."
    set -a  # automatically export all variables
    source <(grep -v '^#' "$PROJECT_ROOT/.env" | grep -v '^$' | sed 's/#.*$//g' | grep '=')
    set +a
    echo "✓ Environment loaded"
else
    echo "⚠ No .env file found at $PROJECT_ROOT/.env"
fi

# Activate conda environment
eval "$(conda shell.bash hook)"
conda activate medparse-py311

# Pass all arguments to the CLI
echo "Running: python -m medparse.cli $@"
python -m medparse.cli "$@"

