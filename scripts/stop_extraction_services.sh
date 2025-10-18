#!/bin/bash
# Stop script for IP Assist Lite extraction services
# This script cleanly shuts down all services started by start_extraction_services.sh

set -e  # Exit on any error

echo "🛑 Stopping IP Assist Lite Extraction Services"
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

# Function to stop service by PID
stop_service_by_pid() {
    local service_name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            print_status "Stopping $service_name (PID: $pid)..."
            kill "$pid"
            sleep 2
            if kill -0 "$pid" 2>/dev/null; then
                print_warning "$service_name didn't stop gracefully, force killing..."
                kill -9 "$pid"
            fi
            print_success "$service_name stopped"
        else
            print_warning "$service_name was not running"
        fi
        rm -f "$pid_file"
    else
        print_warning "$service_name PID file not found"
    fi
}

# Function to stop Docker container
stop_docker_container() {
    local container_name=$1
    local service_name=$2
    
    if docker ps | grep -q "$container_name"; then
        print_status "Stopping $service_name container..."
        docker stop "$container_name" > /dev/null 2>&1
        docker rm "$container_name" > /dev/null 2>&1
        print_success "$service_name container stopped and removed"
    else
        print_warning "$service_name container was not running"
    fi
}

# 1. Stop Medparse FastAPI Service
echo "1️⃣ Stopping Medparse FastAPI Service..."
stop_service_by_pid "medparse" "/tmp/ip_assist_pids/medparse.pid"

# 2. Stop GROBID Container
echo ""
echo "2️⃣ Stopping GROBID Container..."
stop_docker_container "grobid" "GROBID"

# 3. Stop Qdrant Container
echo ""
echo "3️⃣ Stopping Qdrant Container..."
stop_docker_container "ip_assist_qdrant" "Qdrant"

# 4. Clean up PID directory
echo ""
echo "4️⃣ Cleaning up..."
if [ -d "/tmp/ip_assist_pids" ]; then
    rm -rf "/tmp/ip_assist_pids"
    print_success "PID directory cleaned up"
fi

# 5. Clean up log files
if [ -f "/tmp/medparse.log" ]; then
    rm -f "/tmp/medparse.log"
    print_success "Log files cleaned up"
fi

echo ""
print_success "All extraction services stopped successfully!"
echo ""
echo "📋 To start services again: ./scripts/start_extraction_services.sh"
