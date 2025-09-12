#!/bin/bash
# Run IP Assist Lite (Enhanced Version)

echo "Starting IP Assist Lite Enhanced..."
echo "=================================="

# Check if Qdrant is running
if ! curl -s http://localhost:6333/health > /dev/null 2>&1; then
    echo "⚠️  Qdrant not detected. Starting Qdrant..."
    ./scripts/start_qdrant_local.sh &
    sleep 3
fi

# Set default environment variables if not set
export IP_GPT5_MODEL=${IP_GPT5_MODEL:-"gpt-4o-mini"}
export QDRANT_HOST=${QDRANT_HOST:-"localhost"}
export QDRANT_PORT=${QDRANT_PORT:-"6333"}

echo "Configuration:"
echo "  Model: $IP_GPT5_MODEL"
echo "  Qdrant: $QDRANT_HOST:$QDRANT_PORT"
echo ""

# Run the app
python app.py