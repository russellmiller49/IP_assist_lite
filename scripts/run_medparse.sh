#!/bin/bash
# Wrapper script to run medparse CLI with correct Python path

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source <(grep -v '^#' "$PROJECT_ROOT/.env" | grep -v '^$' | sed 's/#.*$//g' | grep '=')
    set +a
fi

# Set Python path to prioritize local medparse
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Activate conda environment and run medparse CLI
conda run -n medparse-py311 python -m medparse.cli "$@"