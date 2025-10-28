#!/bin/bash
# Run medparse CLI with environment variables loaded

# Load environment variables
source "$(dirname "$0")/load_env.sh"

# Activate environment if not already active
if ! python -c "import medparse" 2>/dev/null; then
    echo "Activating medparse-py311 environment..."
    eval "$(conda shell.bash hook)"
    conda activate medparse-py311
fi

# Check QuickUMLS path is accessible
if [ -n "$QUICKUMLS_PATH" ]; then
    if [ -d "$QUICKUMLS_PATH" ]; then
        echo "✓ QuickUMLS path accessible: $QUICKUMLS_PATH"
    else
        echo "⚠ QuickUMLS path does not exist: $QUICKUMLS_PATH"
        echo "  (Database needs to be built if using QuickUMLS)"
    fi
fi

# Run CLI with all arguments
echo "Running medparse CLI..."
python -m medparse.cli "$@"

