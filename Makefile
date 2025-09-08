# IP Assist Lite - Makefile for pipeline execution
.PHONY: help setup prep chunk embed index retrieve api ui test clean all

# Variables
PYTHON := python
CONDA_ENV := ipass2
DATA_DIR := data
SRC_DIR := src

help:
	@echo "IP Assist Lite - Medical Information Retrieval System"
	@echo ""
	@echo "Available targets:"
	@echo "  setup     - Install dependencies and download models"
	@echo "  prep      - Process raw JSON files (standardize, clean, extract)"
	@echo "  chunk     - Create chunks with v2 chunker (policy-driven + QA gate)"
	@echo "  embed     - Generate MedCPT embeddings (requires GPU)"
	@echo "  index     - Build Qdrant index"
	@echo "  retrieve  - Test retrieval pipeline"
	@echo "  api       - Start FastAPI server"
	@echo "  ui        - Start Gradio interface"
	@echo "  test      - Run tests"
	@echo "  clean     - Remove generated files"
	@echo "  all       - Run complete pipeline (prep -> chunk -> embed -> index)"
	@echo ""
	@echo "Docker targets:"
	@echo "  docker-up   - Start Qdrant container"
	@echo "  docker-down - Stop Qdrant container"

# Setup environment
setup:
	@echo "Setting up environment..."
	conda activate $(CONDA_ENV) && pip install -r requirements.txt
	@echo "Downloading spaCy model..."
	conda activate $(CONDA_ENV) && python -m spacy download en_core_web_sm
	@echo "Setup complete!"

# Data preparation
prep:
	@echo "Processing raw documents..."
	cd $(SRC_DIR)/prep && $(PYTHON) data_preparer_v12.py
	@echo "Data preparation complete!"
	@echo "Files processed: $$(ls $(DATA_DIR)/processed/*.json | wc -l)"
	@echo "Registry created: $(DATA_DIR)/registry.jsonl"

# Chunking with v2 chunker and quality gate
chunk:
	@echo "Consolidating processed documents into JSONL..."
	$(PYTHON) $(SRC_DIR)/index/consolidate_docs.py
	@echo "Creating chunks with v2 chunker..."
	$(PYTHON) -m src.index.chunker_v2 \
		--in_jsonl $(DATA_DIR)/processed/documents.jsonl \
		--out_jsonl $(DATA_DIR)/chunks/chunks.jsonl \
		--policy configs/chunking.yaml \
		--tokenizer emilyalsentzer/Bio_ClinicalBERT
	@echo "Running quality gate..."
	$(PYTHON) -m src.index.chunk_quality_gate $(DATA_DIR)/chunks/chunks.qa.csv
	@echo "Chunking complete!"
	@echo "Chunks created: $$(wc -l < $(DATA_DIR)/chunks/chunks.jsonl)"

# Embedding generation
embed:
	@echo "Generating MedCPT embeddings..."
	@echo "Checking GPU availability..."
	@$(PYTHON) -c "import torch; print(f'GPU Available: {torch.cuda.is_available()}'); print(f'GPU Name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
	cd $(SRC_DIR)/index && $(PYTHON) embed_medcpt.py
	@echo "Embeddings generated!"

# Qdrant indexing
index:
	@echo "Building Qdrant index..."
	cd $(SRC_DIR)/index && $(PYTHON) upsert_qdrant.py
	@echo "Index built!"

# Test retrieval
retrieve:
	@echo "Testing retrieval pipeline..."
	cd $(SRC_DIR)/retrieve && $(PYTHON) test_retrieval.py
	@echo "Retrieval test complete!"

# Start API server
api:
	@echo "Starting FastAPI server..."
	cd $(SRC_DIR)/api && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Start Gradio UI
ui:
	@echo "Starting Gradio interface..."
	cd $(SRC_DIR)/ui && $(PYTHON) gradio_app.py

# Run tests
test:
	@echo "Running tests..."
	pytest tests/ -v

# Docker commands
docker-up:
	@echo "Starting Qdrant container..."
	cd docker && docker-compose up -d
	@echo "Qdrant running at http://localhost:6333"

docker-down:
	@echo "Stopping Qdrant container..."
	cd docker && docker-compose down

# Clean generated files
clean:
	@echo "Cleaning generated files..."
	rm -rf $(DATA_DIR)/processed/*
	rm -rf $(DATA_DIR)/chunks/*
	rm -rf $(DATA_DIR)/vectors/*
	rm -rf $(DATA_DIR)/term_index/*
	rm -f $(DATA_DIR)/registry.jsonl
	@echo "Clean complete!"

# Run complete pipeline
all: prep chunk embed index
	@echo "Complete pipeline executed successfully!"

# Development helpers
dev-prep:
	@echo "Running data prep in development mode (first 10 files)..."
	cd $(SRC_DIR)/prep && $(PYTHON) -c "from data_preparer_v12 import DataPreparerV12; p = DataPreparerV12(); files = list(p.input_dir.glob('*.json'))[:10]; [p.process_file(f) for f in files]"

dev-chunk:
	@echo "Running v2 chunking in development mode (first 5 documents)..."
	$(PYTHON) $(SRC_DIR)/index/consolidate_docs.py --dev
	$(PYTHON) -m src.index.chunker_v2 \
		--in_jsonl $(DATA_DIR)/processed/dev_documents.jsonl \
		--out_jsonl $(DATA_DIR)/chunks/dev_chunks.jsonl \
		--policy configs/chunking.yaml
	$(PYTHON) -m src.index.chunk_quality_gate $(DATA_DIR)/chunks/dev_chunks.qa.csv

# Statistics
stats:
	@echo "=== IP Assist Lite Statistics ==="
	@echo "Raw files: $$(ls $(DATA_DIR)/raw/*.json 2>/dev/null | wc -l)"
	@echo "Processed files: $$(ls $(DATA_DIR)/processed/*.json 2>/dev/null | wc -l)"
	@echo "Chunks: $$(wc -l < $(DATA_DIR)/chunks/chunks.jsonl 2>/dev/null || echo 0)"
	@echo "CPT codes indexed: $$(wc -l < $(DATA_DIR)/term_index/cpt.jsonl 2>/dev/null || echo 0)"
	@echo "Aliases indexed: $$(wc -l < $(DATA_DIR)/term_index/aliases.jsonl 2>/dev/null || echo 0)"
	@if [ -f "$(DATA_DIR)/vectors/medcpt_article_embeddings.npy" ]; then \
		echo "Embeddings: Generated"; \
	else \
		echo "Embeddings: Not generated"; \
	fi

# Check system requirements
check-gpu:
	@$(PYTHON) -c "import torch; assert torch.cuda.is_available(), 'GPU not available'; print(f'✓ GPU detected: {torch.cuda.get_device_name(0)}')"

check-deps:
	@$(PYTHON) -c "import torch, transformers, sentence_transformers, qdrant_client, fastapi, gradio; print('✓ All dependencies installed')"

.DEFAULT_GOAL := help