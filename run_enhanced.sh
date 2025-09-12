#!/bin/bash
# Run the enhanced Gradio interface with coding module

echo "🏥 Starting IP Assist Lite Enhanced Edition..."
echo "Features:"
echo "  ✅ Enhanced Query Assistant with conversation support"
echo "  ✅ V3 Procedural Coding Module"
echo "  ✅ Full AMA format citations"
echo ""

# Activate conda environment if available
if command -v conda &> /dev/null; then
    echo "Activating conda environment ipass2..."
    conda activate ipass2
fi

# Set environment variables
export IP_GPT5_MODEL=${IP_GPT5_MODEL:-gpt-4o-mini}
export QDRANT_HOST=${QDRANT_HOST:-localhost}
export QDRANT_PORT=${QDRANT_PORT:-6333}

# Check if Qdrant is running
echo "Checking Qdrant status..."
if curl -s http://$QDRANT_HOST:$QDRANT_PORT/health > /dev/null 2>&1; then
    echo "✅ Qdrant is running"
else
    echo "⚠️  Qdrant not detected. Starting Qdrant..."
    ./scripts/start_qdrant_local.sh &
    sleep 3
fi

# Run the enhanced interface
echo ""
echo "Starting enhanced interface on http://localhost:7861"
echo "Press Ctrl+C to stop"
echo ""

GRADIO_SERVER_PORT=7861 python src/ui/enhanced_gradio_app.py