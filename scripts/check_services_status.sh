#!/bin/bash
# Service status checker for IP Assist Lite extraction services

echo "🔍 IP Assist Lite Service Status Check"
echo "====================================="

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

# Function to check service health
check_service_health() {
    local service_name=$1
    local url=$2
    local port=$3
    
    echo ""
    echo "🔍 Checking $service_name..."
    echo "   URL: $url"
    echo "   Port: $port"
    
    # Check if port is open
    if nc -z localhost $port 2>/dev/null; then
        print_success "Port $port is open"
        
        # Try to get health endpoint
        if curl -s --max-time 5 "$url" > /dev/null 2>&1; then
            print_success "$service_name is healthy and responding"
            
            # Try to get detailed info if available
            case $service_name in
                "Qdrant")
                    echo "   Collections: $(curl -s http://localhost:6333/collections 2>/dev/null | jq -r '.result.collections[].name' 2>/dev/null | tr '\n' ' ' || echo 'Unable to fetch')"
                    ;;
                "Medparse")
                    echo "   Version: $(curl -s http://localhost:8099/version 2>/dev/null | jq -r '.version' 2>/dev/null || echo 'Unable to fetch')"
                    ;;
                "GROBID")
                    echo "   Status: $(curl -s http://localhost:8070/api/isalive 2>/dev/null || echo 'Unable to fetch')"
                    ;;
            esac
        else
            print_warning "$service_name port is open but not responding to health checks"
        fi
    else
        print_error "$service_name is not running (port $port is closed)"
    fi
}

# Function to check Docker containers
check_docker_containers() {
    echo ""
    echo "🐳 Docker Container Status"
    echo "========================="
    
    # Check Qdrant container
    if docker ps | grep -q "ip_assist_qdrant\|qdrant"; then
        print_success "Qdrant container is running"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "ip_assist_qdrant|qdrant"
    else
        print_error "Qdrant container is not running"
    fi
    
    # Check GROBID container
    if docker ps | grep -q "grobid"; then
        print_success "GROBID container is running"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep grobid
    else
        print_warning "GROBID container is not running (optional for basic functionality)"
    fi
}

# Function to check process status
check_process_status() {
    echo ""
    echo "🔧 Process Status"
    echo "================="
    
    # Check Medparse process
    if [ -f "/tmp/ip_assist_pids/medparse.pid" ]; then
        local pid=$(cat /tmp/ip_assist_pids/medparse.pid)
        if kill -0 "$pid" 2>/dev/null; then
            print_success "Medparse process is running (PID: $pid)"
        else
            print_error "Medparse PID file exists but process is not running"
        fi
    else
        print_error "Medparse process not found (no PID file)"
    fi
}

# Function to check IP Assist Lite app
check_ip_assist_app() {
    echo ""
    echo "🚀 IP Assist Lite Application"
    echo "============================="
    
    if nc -z localhost 7860 2>/dev/null; then
        print_success "IP Assist Lite application is running on port 7860"
        echo "   Web UI: http://localhost:7860"
    else
        print_warning "IP Assist Lite application is not running on port 7860"
    fi
}

# Main execution
echo "Checking all services..."

# Check service health endpoints
check_service_health "Qdrant" "http://localhost:6333/health" "6333"
check_service_health "Medparse" "http://localhost:8099/healthz" "8099"
check_service_health "GROBID" "http://localhost:8070/api/isalive" "8070"

# Check Docker containers
check_docker_containers

# Check process status
check_process_status

# Check IP Assist Lite app
check_ip_assist_app

# Summary
echo ""
echo "📋 Summary"
echo "=========="
echo "To start all services: ./scripts/start_extraction_services.sh"
echo "To start full system:  ./scripts/start_full_system.sh"
echo "To stop all services:  ./scripts/stop_extraction_services.sh"
echo ""
echo "Service URLs:"
echo "  • Qdrant:    http://localhost:6333"
echo "  • Medparse:  http://localhost:8099"
echo "  • GROBID:    http://localhost:8070"
echo "  • IP Assist: http://localhost:7860"
