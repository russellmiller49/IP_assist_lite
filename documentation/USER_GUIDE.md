# IP Assist Lite - User Guide

## 📚 Table of Contents
1. [System Overview](#system-overview)
2. [Installation & Setup](#installation--setup)
3. [Ingestion Pipeline (New)](#ingestion-pipeline-new)
4. [Starting the System](#starting-the-system)
5. [Using the Web Interface](#using-the-web-interface)
6. [Using the API](#using-the-api)
7. [Understanding Results](#understanding-results)
8. [Safety Features](#safety-features)
9. [Troubleshooting](#troubleshooting)

## System Overview

IP Assist Lite is a medical information retrieval system designed for Interventional Pulmonology professionals. It provides:

- **Intelligent Search**: Combines semantic understanding, keyword matching, and exact CPT code lookup.
- **Decoupled Ingestion**: Uses a specialized **Medparse Worker** (Dockerized) to extract high-fidelity data from PDFs (Articles, IFUs, Textbooks) using Docling.
- **Medical Authority Ranking**: Prioritizes information from authoritative sources.
- **Safety Guards**: Flags pediatric, dosage, and contraindication information.

## Installation & Setup

### Prerequisites
- Python 3.9+ (for the core app)
- Docker Desktop
- NVIDIA GPU (optional but recommended)

### Step 1: Clone and Environment
```bash
git clone <repository-url>
cd IP_assist_lite

# Core App Environment (Legacy/Spacy based)
conda create -n ipass2 python=3.11
conda activate ipass2
pip install -r requirements.txt
```

### Step 2: Setup Qdrant Database
```bash
docker run -d -p 6333:6333 -p 6334:6334 \
  -v ./qdrant_storage:/qdrant/storage:z \
  --name ip-assistant-qdrant \
  qdrant/qdrant:v1.7.4
```

### Step 3: Build Ingestion Worker (New)
The extraction pipeline now runs in an isolated container to support advanced PDF parsing features (Docling) without conflicting with the main app.

```bash
# Build the ingestion container
docker build -f Dockerfile.ingest -t medparse-ingest .
```

## Ingestion Pipeline (New)

We have moved from a monolithic script to a robust, containerized extraction pipeline.

### 1. Running Extraction
To extract data from a PDF (e.g., an IFU), use the new runner inside the container. The CLI now supports automatic backend routing (`--backend auto`) that probes the PDF for an embedded text layer. Text PDFs run through the classic Medparse engines, while scanned/table-heavy PDFs fall back to Docling+OCR.

```bash
# Syntax
docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/out:/app/out medparse-ingest \
    python -m medparse.pipeline.run_ingest \
    /app/data/Input\ pdfs/my_file.pdf \
    --doc-type ifu \
    --backend auto \
    --output-dir /app/out/extracted

# Example for an IFU
docker run --rm -v $(pwd):/app medparse-ingest \
    python -m medparse.pipeline.run_ingest \
    "data/Input pdfs/ifu_sample.pdf" \
    --doc-type ifu \
    --backend auto
```

**CLI Flags of note**

- `--doc-type {ifu|article|textbook}` routes to the correct Medparse profile.
- `--backend {auto|medparse|docling}` overrides routing when you want to force a path.
- `--version` prints `INGEST_BUILD_SHA=...` so you can confirm which image revision is running.

**GPU & cache hints**

- Add `$(command -v nvidia-smi >/dev/null 2>&1 && echo "--gpus all")` to `docker run` when a GPU is available.
- Mount OCR caches to avoid re-downloading models: `-v "$HOME/.cache/rapidocr":/root/.cache/rapidocr -v "$HOME/.cache/docling":/root/.cache/docling`.
- Disable OCR for text PDFs (the default) via `-e DOCLING_DISABLE_OCR_FOR_TEXT=1`; Docling will only OCR when the text probe fails.
- You can optionally set `-e INGEST_OUT=/output` to force the output directory, but the CLI also honors `--output-dir` for explicit control.

**Batch helpers**

Scripts under `scripts/run_full_*_pipeline.sh` now wrap the container call, pass `--backend auto`, mount caches, and optionally enable GPUs. Run `./scripts/run_full_ifu_pipeline.sh` (or the article/textbook variants) when you need to re-extract entire corpora and feed them through the enrichment/UMLS pass.

### 2. Extraction Artifacts
The pipeline produces JSON files in `out/extracted/` with the following schema:
- **`content_hierarchy`**: Nested tree of sections (Introduction > Indications > ...)
- **`tables`**: Flattened table data converted to natural language sentences (e.g., "The Catheter Diameter is 2.0mm.") for better search retrieval.
- **`safety_warnings`**: Special list of "WARNING", "CAUTION", and "DANGER" boxes detected in the document.

## Extraction Runbook & QA

### Build validation

```bash
docker build -f Dockerfile.ingest \
  --build-arg GIT_SHA=$(git rev-parse --short HEAD) \
  -t medparse-ingest:latest .
docker run --rm medparse-ingest:latest python -m medparse.pipeline.run_ingest --version
# Expect: INGEST_BUILD_SHA=<current_sha>
```

### Smoke the pipelines

```bash
# IFUs (auto backend + smart chunking)
python -m medparse.cli extract-ifus "data/Input pdfs/IFUs/pdf" \
  --out out/ifus --config configs/run_ifu.yaml \
  --profile enriched --no-cache --second-pass auto --chunking smart

# Articles (layout reflow + hygiene benefits)
python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf" \
  --out out/articles --config configs/run_article.yaml \
  --profile enriched --no-cache --second-pass auto \
  --chunking smart --evidence-policy compact \
  --zotero-json data/zotero/my_library.json

# Docker one-off (IFU example)
docker run --rm \
  -v "$PWD/data/Input pdfs/IFUs/pdf":/input \
  -v "$PWD/out/ifus":/output \
  -v "$HOME/.cache/rapidocr":/root/.cache/rapidocr \
  -v "$HOME/.cache/docling":/root/.cache/docling \
  -e INGEST_OUT=/output \
  -e DOCLING_DISABLE_OCR_FOR_TEXT=1 \
  $(command -v nvidia-smi >/dev/null 2>&1 && echo "--gpus all") \
  medparse-ingest:latest python -m medparse.pipeline.run_ingest \
    --doc-type ifu --backend auto /input/ALT-Pro_Instruction\ Manual.pdf
```

### Refresh goldens after QA

```bash
cp -a out/ifus/* tests/_golden/ifus/
cp -a out/articles/* tests/_golden/articles/
```

### Quick regression tests

Run targeted tests locally (or inside the container) after making ingestion changes:

```bash
pytest tests/test_extraction_quality.py \
       tests/layout/test_header_footer_drop.py \
       tests/text/test_hygiene.py
```

## Starting the System

Once data is extracted and indexed (via `make index` which consumes the JSONs), you can run the app.

### Quick Start
```bash
# Ensure Qdrant is running
docker start ip-assistant-qdrant

# Launch App
./launch.sh
```

## Using the Web Interface

### Access the UI
Open your browser and navigate to: **http://localhost:7860**

### Query Assistant Tab
- **Emergency Banner** (Red): Appears for urgent medical situations.
- **Safety Warnings** (Orange): Important safety considerations.
- **Sources**: Clickable citations.

### CPT Code Search Tab
- Enter a 5-digit CPT code (e.g., 31622) to view relevant context and year of publication.

## Using the API

### API Documentation
Interactive documentation available at: **http://localhost:8000/docs**

#### Main Endpoints
- `POST /query`: Process natural language queries.
- `POST /search`: Direct hybrid search.
- `GET /cpt/{code}`: CPT code lookup.

## Understanding Results

### Data Hierarchy
With the new **Medparse** pipeline, results are more granular:
- **Hierarchy**: The system knows if a text chunk comes from "Results" vs "Methods".
- **Tables**: Search can find specific values inside tables (e.g., device dimensions).

## Safety Features

### Automatic Detection
- **Emergency Situations**: Massive hemoptysis, foreign body aspiration.
- **Contraindications**: Absolute and relative.
- **IFU Warnings**: Specific "Boxed Warnings" from device manuals are now explicitly extracted and highlighted.

## Troubleshooting

### Ingestion Issues
- **"File not found"**: Ensure you are mounting the volumes correctly in the `docker run` command (`-v $(pwd):/app`).
- **"Validation failed"**: The document might be scanned or corrupt (check "Gibberish Check" logs).

### System Issues
- **"Qdrant not connected"**: `docker start ip-assistant-qdrant`.
- **GPU OOM**: Reduce batch size in `src/index/embed_medcpt.py`.

### Support
For technical details on the extraction logic, see `medparse/processing.py` and `src/contracts/schema.py`.
