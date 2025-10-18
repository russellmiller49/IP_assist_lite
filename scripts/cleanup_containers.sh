#!/bin/bash
# Cleanup script to remove unnecessary Docker containers
# Keeps only the containers needed for IP Assist Lite

echo "🧹 Cleaning up unnecessary Docker containers"
echo "============================================"

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

# Containers to keep (IP Assist Lite related)
KEEP_CONTAINERS=(
    "ip_assist_qdrant"
    "grobid"
)

# Function to check if container should be kept
should_keep_container() {
    local container_name=$1
    for keep in "${KEEP_CONTAINERS[@]}"; do
        if [[ "$container_name" == *"$keep"* ]]; then
            return 0  # Keep this container
        fi
    done
    return 1  # Remove this container
}

# Get all stopped containers
print_status "Finding stopped containers..."
STOPPED_CONTAINERS=$(docker ps -a --filter "status=exited" --format "{{.Names}}")
CREATED_CONTAINERS=$(docker ps -a --filter "status=created" --format "{{.Names}}")

ALL_CONTAINERS="$STOPPED_CONTAINERS $CREATED_CONTAINERS"

if [ -z "$ALL_CONTAINERS" ]; then
    print_success "No stopped or created containers found to clean up!"
    exit 0
fi

echo ""
print_status "Containers to be removed:"
echo "================================"

REMOVE_LIST=()
for container in $ALL_CONTAINERS; do
    if ! should_keep_container "$container"; then
        echo "  • $container"
        REMOVE_LIST+=("$container")
    else
        print_warning "Keeping: $container"
    fi
done

if [ ${#REMOVE_LIST[@]} -eq 0 ]; then
    print_success "No containers need to be removed!"
    exit 0
fi

echo ""
echo "Total containers to remove: ${#REMOVE_LIST[@]}"
echo ""

# Ask for confirmation
read -p "Do you want to proceed with removing these containers? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Cleanup cancelled."
    exit 0
fi

echo ""
print_status "Removing containers..."

REMOVED_COUNT=0
FAILED_COUNT=0

for container in "${REMOVE_LIST[@]}"; do
    print_status "Removing $container..."
    if docker rm "$container" 2>/dev/null; then
        print_success "Removed $container"
        ((REMOVED_COUNT++))
    else
        print_error "Failed to remove $container"
        ((FAILED_COUNT++))
    fi
done

echo ""
echo "📊 Cleanup Summary"
echo "=================="
print_success "Successfully removed: $REMOVED_COUNT containers"
if [ $FAILED_COUNT -gt 0 ]; then
    print_error "Failed to remove: $FAILED_COUNT containers"
fi

echo ""
print_status "Current running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
print_status "To clean up unused images and volumes:"
echo "  docker system prune -a"
echo "  docker volume prune"
