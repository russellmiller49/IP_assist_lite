#!/bin/bash
# Complete startup script for IP Assist Lite extraction services
# This script starts all necessary containers and services for PDF extraction

set -e  # Exit on any error

echo "🚀 Starting IP Assist Lite Extraction Services"
echo "=============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if a service is running
check_service() {
    local url=$1
    local service_name=$2
    local max_attempts=${3:-10}
    
    print_status "Checking $service_name health..."
    for i in $(seq 1 $max_attempts); do
        if curl -s "$url" > /dev/null 2>&1; then
            print_success "$service_name is ready!"
            return 0
        fi
        echo "   Waiting... ($i/$max_attempts)"
        sleep 2
    done
    print_error "$service_name failed to start"
    return 1
}

# Function to start service in background and capture PID
start_background_service() {
    local service_name=$1
    local command=$2
    local pid_file=$3
    
    print_status "Starting $service_name..."
    eval "$command" > "/tmp/${service_name}.log" 2>&1 &
    echo $! > "$pid_file"
    print_success "$service_name started (PID: $(cat $pid_file))"
}

# Get the project root directory
PROJECT_ROOT="/home/rjm/projects/IP_assist_lite"
MEDPARSE_ROOT="/home/rjm/projects/ip_knowledge/medparse/medparse-docling"

# Change to project root
cd "$PROJECT_ROOT"

# Create PID directory
mkdir -p /tmp/ip_assist_pids

print_status "Project root: $PROJECT_ROOT"
print_status "Medparse root: $MEDPARSE_ROOT"

# 1. Start Qdrant
echo ""
echo "1️⃣ Starting Qdrant Vector Database..."
if docker ps | grep -q "qdrant\|ip_assist_qdrant"; then
    print_warning "Qdrant container already running"
else
    print_status "Starting Qdrant container..."
    docker run -d \
        --name ip_assist_qdrant \
        -p 6333:6333 \
        -p 6334:6334 \
        -v "$(pwd)/data/qdrant_storage:/qdrant/storage" \
        qdrant/qdrant:v1.8.2 > /dev/null 2>&1
    
    if check_service "http://localhost:6333/health" "Qdrant" 15; then
        print_success "Qdrant is ready!"
    else
        print_error "Qdrant failed to start. Check Docker logs: docker logs ip_assist_qdrant"
        exit 1
    fi
fi

# 2. Start GROBID (optional but recommended for full PDF processing)
echo ""
echo "2️⃣ Starting GROBID PDF Processor..."
if docker ps | grep -q "grobid"; then
    print_warning "GROBID container already running"
else
    print_status "Starting GROBID container..."
    docker run -d \
        --name grobid \
        -p 8070:8070 \
        lfoppiano/grobid:0.8.0 > /dev/null 2>&1
    
    if check_service "http://localhost:8070/api/isalive" "GROBID" 20; then
        print_success "GROBID is ready!"
    else
        print_warning "GROBID failed to start. PDF processing may be limited."
        print_warning "Check Docker logs: docker logs grobid"
    fi
fi

# 3. Start Medparse FastAPI Service
echo ""
echo "3️⃣ Starting Medparse FastAPI Service..."
if [ -f "/tmp/ip_assist_pids/medparse.pid" ] && kill -0 "$(cat /tmp/ip_assist_pids/medparse.pid)" 2>/dev/null; then
    print_warning "Medparse service already running (PID: $(cat /tmp/ip_assist_pids/medparse.pid))"
else
    # Check if medparse environment exists
    if ! conda env list | grep -q "medparse-py311"; then
        print_error "medparse-py311 conda environment not found!"
        print_error "Please create it first: conda create -n medparse-py311 python=3.11 -y"
        exit 1
    fi
    
    # Start Medparse in background
    cd "$MEDPARSE_ROOT"
    start_background_service "medparse" \
        "conda run -n medparse-py311 uvicorn api.main:app --host 0.0.0.0 --port 8099" \
        "/tmp/ip_assist_pids/medparse.pid"
    
    cd "$PROJECT_ROOT"
    
    if check_service "http://localhost:8099/healthz" "Medparse" 15; then
        print_success "Medparse is ready!"
    else
        print_error "Medparse failed to start. Check logs: tail -f /tmp/medparse.log"
        exit 1
    fi
fi

# 4. Verify all services are running
echo ""
echo "4️⃣ Final Health Check..."
echo "========================"

services=(
    "Qdrant:http://localhost:6333/health"
    "GROBID:http://localhost:8070/api/isalive"
    "Medparse:http://localhost:8099/healthz"
)

all_healthy=true
for service in "${services[@]}"; do
    IFS=':' read -r name url <<< "$service"
    if curl -s "$url" > /dev/null 2>&1; then
        print_success "$name is healthy"
    else
        print_error "$name is not responding"
        all_healthy=false
    fi
done

echo ""
if [ "$all_healthy" = true ]; then
    print_success "All services are running and healthy!"
    echo ""
    echo "📋 Service URLs:"
    echo "   • Qdrant: http://localhost:6333"
    echo "   • GROBID: http://localhost:8070"
    echo "   • Medparse: http://localhost:8099"
    echo ""
    echo "🚀 Ready to start IP Assist Lite application:"
    echo "   cd $PROJECT_ROOT"
    echo "   conda activate ip-assist"
    echo "   export MEDPARSE_URL=http://127.0.0.1:8099"
    echo "   python app.py"
    echo ""
    echo "📝 Service PIDs saved in /tmp/ip_assist_pids/"
    echo "📋 To stop all services: ./scripts/stop_extraction_services.sh"
else
    print_error "Some services failed to start. Please check the logs above."
    exit 1
fi
