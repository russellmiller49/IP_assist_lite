#!/bin/bash
#set -e

# --- Configuration ---
INPUT_DIR="/home/rjm/projects/IP_assist_lite/data/Input pdfs/IFUs/pdf"
INTERMEDIATE_DIR="/home/rjm/projects/IP_assist_lite/out/ifus_intermediate"
FINAL_OUTPUT_DIR="/home/rjm/projects/IP_assist_lite/out/ifus"

# Ensure directories exist
mkdir -p "$INTERMEDIATE_DIR"
mkdir -p "$FINAL_OUTPUT_DIR"

# Clean output directories to prevent stale/duplicate files
echo "Cleaning output directories..."
rm -rf "$INTERMEDIATE_DIR"/*
rm -rf "$FINAL_OUTPUT_DIR"/*

echo "=================================================="
echo "Starting Full IFU Pipeline"
echo "Input: $INPUT_DIR"
echo "Intermediate Output: $INTERMEDIATE_DIR"
echo "Final Output: $FINAL_OUTPUT_DIR"
echo "=================================================="

# --- Step 1: Extraction (Docker Container) ---
echo ""
echo "--- Step 1: Running Extraction (Medparse Ingest Docker) ---"
echo "This step extracts text, hierarchy, and tables using Docling."

# Check if Docker image exists, if not, prompt to build
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

set -e
docker run --rm $GPU_ARGS \
    -e DOCLING_DISABLE_OCR_FOR_TEXT=1 \
    -e INGEST_OUT=/output \
    -v "$HOME/.cache/rapidocr":/root/.cache/rapidocr \
    -v "$HOME/.cache/docling":/root/.cache/docling \
    -v "$INPUT_DIR":/input:ro \
    -v "$INTERMEDIATE_DIR":/output \
    medparse-ingest \
    python -m medparse.pipeline.run_ingest \
    /input \
    --doc-type ifu \
    --backend auto

echo "Extraction complete. Intermediate JSONs saved to $INTERMEDIATE_DIR"

# --- Step 2: Enrichment (Local Python) ---
echo ""
echo "--- Step 2: Running UMLS Enrichment (Local Python) ---"
echo "This step adds medical entity links using QuickUMLS."

# Check for QuickUMLS path
if [ -z "$QUICKUMLS_PATH" ]; then
    export QUICKUMLS_PATH="/home/rjm/quickumls_data"
    echo "QUICKUMLS_PATH not set, using default: $QUICKUMLS_PATH"
fi

# Run the python enrichment script
# Ensure we are in the right conda environment or have dependencies
python scripts/enrich_json_with_umls.py "$INTERMEDIATE_DIR" "$FINAL_OUTPUT_DIR"

echo ""
echo "=================================================="
echo "Pipeline Complete!"
echo "Final enriched files are in: $FINAL_OUTPUT_DIR"
echo "=================================================="
