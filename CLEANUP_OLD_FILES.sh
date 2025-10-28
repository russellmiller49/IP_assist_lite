#!/bin/bash
# Clean up old/temporary documentation files

cd /home/rjm/projects/IP_assist_lite

echo "=== Cleaning Up Old Documentation Files ==="
echo ""

# Files to delete (obsolete/temporary)
FILES_TO_DELETE=(
    "ENVIRONMENT_SETUP_COMPLETE.md"
    "ENV_LOADING_FIXED.md"
    "ENV_LOADING_GUIDE.md"
    "FINAL_VERIFICATION_COMPLETE.md"
    "CONDA_INIT_FIX.md"
    "SETUP_COMPLETE_SUMMARY.md"
    "INSTALLATION_COMPLETE.md"
    "QUICKUMLS_SETUP.md"
    "QUICKUMLS_STATUS.md"
    "UMLS_COPY_COMPLETE.md"
    "WORKAROUND_SOLUTION.md"
    "SIMPLE_SOLUTION.md"
    "FIX_EMPTY_ENVIRONMENT.md"
    "FIX_MEDPARSE_PY311.md"
    "ENVIRONMENT_CLEANUP.md"
    "CURRENT_STATUS.md"
    "FINAL_STATUS.md"
    "BATCH_EXTRACTION_READY.md"
    "ENVIRONMENT_CLARIFICATION.md"
    "HANDOFF_NEXT_SESSION.md"
    "MIGRATION_NOTES.md"
    "PATCH_STATUS.md"
    "IMPLEMENTATION_COMPLETE.md"
    "IMPLEMENTATION_STATUS.md"
    "IMPLEMENTATION_SUMMARY.md"
    "DEPENDENCIES.md"
    "SETUP_SUMMARY.md"
)

echo "Files to delete:"
for file in "${FILES_TO_DELETE[@]}"; do
    if [ -f "$file" ]; then
        echo "  - $file"
    fi
done

echo ""
read -p "Delete these files? (y/N) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    for file in "${FILES_TO_DELETE[@]}"; do
        if [ -f "$file" ]; then
            rm -v "$file"
        fi
    done
    echo ""
    echo "✓ Cleanup complete!"
    echo ""
    echo "Kept files:"
    echo "  - README.md"
    echo "  - CHANGELOG.md"
    echo "  - QUICK_START.md (updated)"
    echo "  - SETUP_GUIDE.md (new)"
    echo "  - BATCH_EXTRACTION.md (new)"
    echo "  - _CLEANUP_PLAN.md"
    echo "  - docs/ folder"
    echo "  - documentation/ folder"
else
    echo "Cleanup cancelled"
fi

