#!/bin/bash
# Start Qdrant locally without Docker

echo "🚀 Starting Qdrant Locally (No Docker)"
echo "======================================"

# Check if Qdrant is installed
if ! command -v qdrant &> /dev/null; then
    echo "📦 Qdrant not found. Installing..."
    
    # Download Qdrant binary for macOS (detect architecture)
    echo "Downloading Qdrant for macOS..."
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        echo "Detected Apple Silicon (ARM64)"
        curl -L https://github.com/qdrant/qdrant/releases/download/v1.7.4/qdrant-aarch64-apple-darwin.tar.gz -o qdrant.tar.gz
    else
        echo "Detected Intel (x86_64)"
        curl -L https://github.com/qdrant/qdrant/releases/download/v1.7.4/qdrant-x86_64-apple-darwin.tar.gz -o qdrant.tar.gz
    fi
    
    # Extract
    tar -xzf qdrant.tar.gz
    
    # Move to local bin
    mkdir -p ./bin
    mv qdrant ./bin/
    rm qdrant.tar.gz
    
    echo "✅ Qdrant downloaded to ./bin/qdrant"
fi

# Start Qdrant
echo "Starting Qdrant server..."
./bin/qdrant --storage-dir ./data/qdrant_storage &

# Save PID
echo $! > qdrant.pid

# Wait for Qdrant to start
echo "Waiting for Qdrant to be ready..."
for i in {1..10}; do
    curl -s http://localhost:6333/health > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Qdrant is ready!"
        echo "PID: $(cat qdrant.pid)"
        echo ""
        echo "To stop Qdrant later: kill $(cat qdrant.pid)"
        exit 0
    fi
    echo "Waiting... ($i/10)"
    sleep 2
done

echo "❌ Qdrant failed to start"
exit 1