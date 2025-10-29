#!/bin/bash
# Clear medparse cache to regenerate sklearn models with current version

CACHE_DIR="/home/rjm/projects/ip_knowledge/medparse/medparse-docling/cache"

if [ ! -d "$CACHE_DIR" ]; then
    echo "Cache directory not found: $CACHE_DIR"
    exit 1
fi

echo "=== Clearing Medparse Cache ==="
echo ""
echo "Cache directory: $CACHE_DIR"

# Count files
FILE_COUNT=$(find "$CACHE_DIR" -name "*.pkl" | wc -l)
echo "Found $FILE_COUNT .pkl files"

if [ "$FILE_COUNT" -eq 0 ]; then
    echo "No cache files to clear"
    exit 0
fi

echo ""
read -p "Clear all cache files? This will force regeneration with sklearn 1.7.2 (y/N) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Clearing cache..."
    find "$CACHE_DIR" -name "*.pkl" -delete
    echo "✓ Cache cleared"
    echo ""
    echo "Cache will be regenerated automatically on next extraction run"
    echo "New cache files will use sklearn 1.7.2"
else
    echo "Cache clearing cancelled"
fi

