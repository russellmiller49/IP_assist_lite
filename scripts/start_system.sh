#!/bin/bash
# Complete system startup script for IP Assist Lite

echo "🚀 Starting IP Assist Lite System"
echo "=================================="

# 1. Start Qdrant vector database
echo "1️⃣ Starting Qdrant vector database..."
docker ps | grep qdrant > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "   ✅ Qdrant already running"
else
    echo "   Starting Qdrant container..."
    docker run -d \
        --name qdrant \
        -p 6333:6333 \
        -v $(pwd)/data/qdrant_storage:/qdrant/storage \
        qdrant/qdrant:latest
    
    # Wait for Qdrant to be ready
    echo "   Waiting for Qdrant to be ready..."
    for i in {1..10}; do
        curl -s http://localhost:6333/health > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "   ✅ Qdrant is ready!"
            break
        fi
        echo "   Waiting... ($i/10)"
        sleep 2
    done
fi

# 2. Verify Qdrant health
echo ""
echo "2️⃣ Verifying Qdrant health..."
curl -s http://localhost:6333/health | python -m json.tool
if [ $? -ne 0 ]; then
    echo "   ❌ Qdrant is not healthy. Please check Docker."
    echo "   Run: docker logs qdrant"
    exit 1
fi

# 3. Check if index exists
echo ""
echo "3️⃣ Checking Qdrant collections..."
curl -s http://localhost:6333/collections | python -m json.tool | grep ip_assist_lite > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "   ✅ Collection 'ip_assist_lite' exists"
else
    echo "   ⚠️  Collection 'ip_assist_lite' not found"
    echo "   You may need to run indexing: make index"
fi

echo ""
echo "✅ System components ready!"
echo ""
echo "📋 Next steps:"
echo "   1. If collection is missing: make index"
echo "   2. Run the app: PYTHONPATH=src python -m ui.gradio_app"
echo "   3. Or use CLI: python cli_interface.py"
