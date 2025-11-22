#!/bin/bash
#set -e

# --- Configuration ---
# Base directory containing subfolders for each textbook
TEXTBOOK_BASE_DIR="/home/rjm/projects/IP_assist_lite/data/Input pdfs/Texbooks"
INTERMEDIATE_DIR="/home/rjm/projects/IP_assist_lite/out/textbooks_intermediate"
FINAL_OUTPUT_DIR="/home/rjm/projects/IP_assist_lite/out/textbooks"

# Ensure output directories exist
mkdir -p "$INTERMEDIATE_DIR"
mkdir -p "$FINAL_OUTPUT_DIR"

# Clean output directories to prevent stale/duplicate files
echo "Cleaning output directories..."
rm -rf "$INTERMEDIATE_DIR"/*
rm -rf "$FINAL_OUTPUT_DIR"/*

echo "=================================================="
echo "Starting Full Textbook Pipeline"
echo "Base Input: $TEXTBOOK_BASE_DIR"
echo "Intermediate Output: $INTERMEDIATE_DIR"
echo "Final Output: $FINAL_OUTPUT_DIR"
echo "=================================================="

# --- Step 1: Extraction (Docker Container) ---
echo ""
echo "--- Step 1: Running Extraction (Medparse Ingest Docker) ---"

if [[ "$(docker images -q medparse-ingest 2> /dev/null)" == "" ]]; then
  echo "Docker image 'medparse-ingest' not found. Building it now..."
  docker build -f Dockerfile.ingest -t medparse-ingest .
fi

echo "Preparing ingestion container..."
mkdir -p "$HOME/.cache/rapidocr"
mkdir -p "$HOME/.cache/docling"

GPU_ARGS=""
if command -v nvidia-smi >/dev/null 2>&1; then
    if nvidia-smi >/dev/null 2>&1; then
        GPU_ARGS="--gpus all"
    fi
fi

total_count=0

# Find all subdirectories in the base folder
find "$TEXTBOOK_BASE_DIR" -mindepth 1 -maxdepth 1 -type d | while read -r textbook_folder; do
    textbook_name=$(basename "$textbook_folder")
    echo ""
    echo ">>> Processing Textbook: $textbook_name"
    
    # Process each PDF chapter in this folder
    shopt -s nullglob
    chapter_pdfs=("$textbook_folder"/*.pdf)
    
    for pdf_file in "${chapter_pdfs[@]}"; do
        chapter_filename=$(basename "$pdf_file")
        echo "    Extracting Chapter: $chapter_filename"
        
        # We mount the specific textbook folder as /input
        # Note: Removing --metadata-file as it is not supported by current run_ingest.py
        docker run --rm $GPU_ARGS \
            -e DOCLING_DISABLE_OCR_FOR_TEXT=1 \
            -e INGEST_OUT=/output \
            -v "$HOME/.cache/rapidocr":/root/.cache/rapidocr \
            -v "$HOME/.cache/docling":/root/.cache/docling \
            -v "$textbook_folder":/input:ro \
            -v "$INTERMEDIATE_DIR":/output \
            medparse-ingest \
            python -m medparse.pipeline.run_ingest \
            "/input/$chapter_filename" \
            --doc-type textbook \
            --backend auto \
            --output-dir /output
            
        total_count=$((total_count + 1))
    done
done

if [ "$total_count" -eq 0 ]; then
    echo "No PDF chapters found in any subfolders of $TEXTBOOK_BASE_DIR"
    # Try looking in the base directory itself if no subfolders had pdfs or no subfolders existed
    shopt -s nullglob
    base_pdfs=("$TEXTBOOK_BASE_DIR"/*.pdf)
    if [ ${#base_pdfs[@]} -gt 0 ]; then
        echo "Found PDFs in base directory, processing them..."
        for pdf_file in "${base_pdfs[@]}"; do
             chapter_filename=$(basename "$pdf_file")
             echo "    Extracting: $chapter_filename"
             docker run --rm $GPU_ARGS \
                -e DOCLING_DISABLE_OCR_FOR_TEXT=1 \
                -e INGEST_OUT=/output \
                -v "$HOME/.cache/rapidocr":/root/.cache/rapidocr \
                -v "$HOME/.cache/docling":/root/.cache/docling \
                -v "$TEXTBOOK_BASE_DIR":/input:ro \
                -v "$INTERMEDIATE_DIR":/output \
                medparse-ingest \
                python -m medparse.pipeline.run_ingest \
                "/input/$chapter_filename" \
                --doc-type textbook \
                --backend auto \
                --output-dir /output
        done
    else
        echo "No PDFs found to process."
    fi
fi

echo ""
echo "Extraction complete. Intermediate JSONs saved to $INTERMEDIATE_DIR"

# --- Step 2: Enrichment (Local Python) ---
echo ""
echo "--- Step 2: Running UMLS Enrichment (Local Python) ---"

if [ -z "$QUICKUMLS_PATH" ]; then
    export QUICKUMLS_PATH="/home/rjm/quickumls_data"
    echo "QUICKUMLS_PATH not set, using default: $QUICKUMLS_PATH"
fi

# Run enrichment on all extracted chapters
python scripts/enrich_json_with_umls.py "$INTERMEDIATE_DIR" "$FINAL_OUTPUT_DIR"

echo ""
echo "=================================================="
echo "Pipeline Complete!"
echo "Final enriched files are in: $FINAL_OUTPUT_DIR"
echo "=================================================="
