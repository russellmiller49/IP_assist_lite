#!/bin/bash

# IP Assist Lite Launcher Script

echo "🏥 IP Assist Lite - Starting Services"
echo "====================================="

# Check if Qdrant is running
echo "Checking Qdrant status..."
if ! curl -s http://localhost:6333/health > /dev/null; then
    echo "⚠️  Qdrant is not running. Starting Qdrant..."
    docker start ip-assistant-qdrant || echo "Failed to start Qdrant. Please run: make docker-up"
    sleep 3
fi

# Function to cleanup on exit
cleanup() {
    echo -e "\n\n🛑 Shutting down services..."
    kill $FASTAPI_PID $GRADIO_PID 2>/dev/null
    exit 0
}

trap cleanup INT TERM

# Start FastAPI in background
echo "Starting FastAPI server on port 8000..."
cd /home/rjm/projects/IP_assist_lite/src/api
python fastapi_app.py &
FASTAPI_PID=$!
echo "FastAPI PID: $FASTAPI_PID"

# Wait for FastAPI to start
sleep 5

# Start Gradio in background
echo "Starting Gradio UI on port 7860..."
cd /home/rjm/projects/IP_assist_lite/src/ui
python gradio_app.py &
GRADIO_PID=$!
echo "Gradio PID: $GRADIO_PID"

echo ""
echo "====================================="
echo "✅ Services Started Successfully!"
echo "====================================="
echo ""
echo "📍 Access Points:"
echo "  • Gradio UI:    http://localhost:7860"
echo "  • FastAPI Docs: http://localhost:8000/docs"
echo "  • API Health:   http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for processes
wait $FASTAPI_PID $GRADIO_PID