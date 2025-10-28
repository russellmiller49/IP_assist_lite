#!/bin/bash
# Load environment variables from .env file

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env file if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "Loading environment from $PROJECT_ROOT/.env"
    # Use set -a to automatically export all variables
    set -a
    source <(grep -v '^#' "$PROJECT_ROOT/.env" | grep -v '^$' | sed 's/#.*$//g' | grep '=')
    set +a
    echo "✓ Environment variables loaded"
    
    # Show key variables (masked)
    if [ -n "$UMLS_API_KEY" ]; then
        echo "  UMLS_API_KEY: ${UMLS_API_KEY:0:20}... (set)"
    fi
    if [ -n "$QUICKUMLS_PATH" ]; then
        echo "  QUICKUMLS_PATH: $QUICKUMLS_PATH"
    fi
else
    echo "⚠ No .env file found at $PROJECT_ROOT/.env"
fi

