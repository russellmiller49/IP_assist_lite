#!/bin/bash
# Script to create a minimal branch by removing large non-essential files

set -e

REPO_DIR="/home/rjm/projects/IP_assist_lite"
cd "$REPO_DIR"

echo "=== IP Assist Lite - Minimal Branch Creator ==="
echo ""

# Check current branch
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "Current branch: $CURRENT_BRANCH"
echo ""

# List all branches
echo "Available branches:"
git branch -a
echo ""

# Ask for branch name (or use current)
read -p "Enter name for minimal branch (or press Enter to use current branch): " MINIMAL_BRANCH
if [ -z "$MINIMAL_BRANCH" ]; then
    MINIMAL_BRANCH="${CURRENT_BRANCH}-minimal"
    echo "Using: $MINIMAL_BRANCH"
fi

# Check if branch exists
if git show-ref --verify --quiet refs/heads/"$MINIMAL_BRANCH"; then
    echo "Branch $MINIMAL_BRANCH already exists!"
    read -p "Do you want to delete and recreate it? (y/N): " RECREATE
    if [ "$RECREATE" != "y" ]; then
        echo "Aborted."
        exit 1
    fi
    git branch -D "$MINIMAL_BRANCH" 2>/dev/null || true
fi

# Create new branch from current
echo "Creating branch: $MINIMAL_BRANCH"
git checkout -b "$MINIMAL_BRANCH"

echo ""
echo "=== Finding large files ==="
echo ""

# Find large files (>500KB)
find . -type f -size +500k ! -path './.git/*' ! -path './.hypothesis/*' -exec ls -lh {} \; | \
    awk '{print $5, $9}' | sort -hr > /tmp/large_files.txt

echo "Large files found:"
head -30 /tmp/large_files.txt
echo ""

# Calculate current size
CURRENT_SIZE=$(du -sh . 2>/dev/null | cut -f1)
echo "Current repository size: $CURRENT_SIZE"
echo ""

echo "=== Files to remove (non-essential large files) ==="
echo ""

# Categories of files to remove
REMOVE_PATTERNS=(
    "data/Input pdfs/*.pdf"           # PDFs can be regenerated
    "data/seed/*.pdf"                  # Seed PDFs
    "data/vectors/*.npy"               # Large numpy arrays (embeddings)
    "data/processed/*.json"            # Processed data (can be regenerated)
    "data/chunks/*.jsonl"              # Chunk files
    "data/structured_knowledge/*.json" # Structured knowledge (can be regenerated)
    "data/term_index/*.jsonl"          # Term index files
    "data/registry.jsonl"               # Registry file
    "bin/qdrant"                       # Binary (users should install separately)
    "models/*.joblib"                  # Model files (can be downloaded)
    "tests/**/*.pdf"                    # Test PDFs (keep small samples)
    ".hypothesis/*"                     # Hypothesis test data
    "out/*.json"                        # Output files
    "anomaly_reports/*"                 # Anomaly reports
    "Claude_chat_transcripts/*"         # Chat transcripts
    "cursor_exported_coversations/*"    # Exported conversations
    "*.txt:Zone.Identifier"            # Windows zone identifiers
)

# Create a list of files to remove
REMOVE_LIST="/tmp/files_to_remove.txt"
> "$REMOVE_LIST"

for pattern in "${REMOVE_PATTERNS[@]}"; do
    # Expand pattern and add to remove list
    find . -path "./.git" -prune -o -type f -path "$pattern" -print >> "$REMOVE_LIST" 2>/dev/null || true
done

# Also find large files in specific directories
find . -type f -size +1M \
    -path "./data/*" \
    ! -path "./data/schema/*" \
    ! -path "./data/templates/*" \
    ! -path "./data/fixtures/*" \
    -print >> "$REMOVE_LIST" 2>/dev/null || true

# Remove duplicates and sort
sort -u "$REMOVE_LIST" > "${REMOVE_LIST}.sorted"
mv "${REMOVE_LIST}.sorted" "$REMOVE_LIST"

echo "Files to be removed:"
wc -l "$REMOVE_LIST"
echo ""
echo "Sample files to remove:"
head -20 "$REMOVE_LIST"
echo ""

read -p "Proceed with removal? (y/N): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo "Aborted."
    exit 1
fi

# Remove files
echo ""
echo "=== Removing files ==="
while IFS= read -r file; do
    if [ -f "$file" ]; then
        echo "Removing: $file"
        rm -f "$file"
    fi
done < "$REMOVE_LIST"

# Remove empty directories
echo ""
echo "=== Cleaning empty directories ==="
find . -type d -empty ! -path "./.git/*" -delete 2>/dev/null || true

# Stage removals
echo ""
echo "=== Staging changes ==="
git add -A

# Show status
echo ""
echo "=== Git status ==="
git status --short | head -30
echo ""

# Calculate new size
NEW_SIZE=$(du -sh . 2>/dev/null | cut -f1)
echo "New repository size: $NEW_SIZE"
echo ""

# Commit
read -p "Commit changes? (y/N): " COMMIT
if [ "$COMMIT" == "y" ]; then
    git commit -m "Create minimal branch: Remove large non-essential files
    
    - Removed PDF files (can be regenerated via ingestion)
    - Removed processed data files (can be regenerated)
    - Removed vector embeddings (can be regenerated)
    - Removed binary files (bin/qdrant - install separately)
    - Removed model files (can be downloaded)
    - Removed test data and output files
    - Kept all source code and essential configuration
    
    This branch is optimized for code review and understanding
    the repository structure without large data files."
    
    echo ""
    echo "=== Branch created successfully! ==="
    echo "Branch: $MINIMAL_BRANCH"
    echo "To push to GitHub:"
    echo "  git push origin $MINIMAL_BRANCH"
    echo ""
    echo "To switch back to original branch:"
    echo "  git checkout $CURRENT_BRANCH"
else
    echo "Changes staged but not committed."
    echo "You can review with: git status"
    echo "Commit manually when ready."
fi
