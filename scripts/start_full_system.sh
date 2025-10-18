#!/bin/bash
# Complete system startup - starts all services and launches IP Assist Lite app

set -e  # Exit on any error

echo "🚀 Starting Complete IP Assist Lite System"
echo "=========================================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the project root directory
PROJECT_ROOT="/home/rjm/projects/IP_assist_lite"

# Change to project root
cd "$PROJECT_ROOT"

# Start all extraction services
echo -e "${BLUE}Starting extraction services...${NC}"
./scripts/start_extraction_services.sh

# Check if services started successfully
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ All services started successfully!${NC}"
    echo ""
    echo "🚀 Starting IP Assist Lite application..."
    echo "========================================"
    
    # Set environment variables
    export MEDPARSE_URL=http://127.0.0.1:8099
    export MEDPARSE_ENABLED=true
    
    # Check if ip-assist conda environment exists
    if conda env list | grep -q "ip-assist"; then
        echo "Activating ip-assist conda environment..."
        conda activate ip-assist
        echo "Starting Gradio application..."
        python app.py
    else
        echo "❌ ip-assist conda environment not found!"
        echo "Please create it first:"
        echo "  conda create -n ip-assist python=3.12 -y"
        echo "  conda activate ip-assist"
        echo "  pip install -r requirements.txt"
        exit 1
    fi
else
    echo "❌ Failed to start extraction services. Please check the logs above."
    exit 1
fi
