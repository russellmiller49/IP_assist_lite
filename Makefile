# IP Assist Lite / Medparse Makefile
.PHONY: help setup test cov format lint typecheck batch \
 legacy-setup legacy-test prep chunk embed index retrieve api ui clean all \
 kb-setup kb-extract kb-generate kb-validate kb-chunks kb-embed kb-all \
 graph-up graph-down backfill graph-validate

# Variables
PYTHON := python
CONDA_ENV := ipass
DATA_DIR := data
SRC_DIR := src

help:
	@echo "IP Assist Lite - Medical Information Retrieval System"
	@echo ""
	@echo "Medparse targets:"
	@echo "  setup       - Install dependencies for Medparse and register pre-commit hooks"
	@echo "  test        - Run Medparse unit and integration tests"
	@echo "  cov         - Run tests with coverage reporting"
	@echo "  format      - Format Medparse code (black + isort)"
	@echo "  lint        - Run Ruff lint checks"
	@echo "  typecheck   - Run mypy static analysis"
	@echo "  batch       - Execute batch extraction pipeline (INPUT=, OUTPUT=)"
	@echo ""
	@echo "Legacy IP Assist targets remain available (legacy-setup, legacy-test, prep, chunk, ...)."
	@echo "Run 'make legacy-setup' for the original environment bootstrap."

# ---------------------------------------------------------------------------
# Medparse tooling

setup:
	@echo "Installing Medparse dependencies..."
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]
	@echo "Registering pre-commit hooks..."
	pre-commit install --install-hooks
	@echo "Medparse setup complete."

test:
	@echo "Running Medparse tests..."
	$(PYTHON) -m pytest

cov:
	@echo "Running Medparse tests with coverage..."
	$(PYTHON) -m pytest --cov=medparse --cov-report=term-missing

format:
	@echo "Formatting Medparse code..."
	$(PYTHON) -m black medparse tests/unit tests/integration
	$(PYTHON) -m isort medparse tests/unit tests/integration

lint:
	@echo "Linting Medparse code..."
	$(PYTHON) -m ruff check medparse tests/unit tests/integration

typecheck:
	@echo "Running mypy..."
	$(PYTHON) -m mypy medparse

batch:
ifndef INPUT
	$(error INPUT is not set. Usage: make batch INPUT=path/to/pdfs OUTPUT=out_dir)
endif
ifndef OUTPUT
	$(error OUTPUT is not set. Usage: make batch INPUT=path/to/pdfs OUTPUT=out_dir)
endif
	@echo "Running Medparse batch extraction..."
	$(PYTHON) -m medparse.batch.run --input "$(INPUT)" --output "$(OUTPUT)"
	@echo "Batch extraction finished."

# ---------------------------------------------------------------------------
# Legacy pipeline (retained for backward compatibility)

legacy-setup:
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
	PYTHONPATH=src $(PYTHON) -m ui.gradio_app

# Run tests
legacy-test:
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

graph-up:
	@echo "Starting Neo4j + Qdrant stack..."
	docker compose -f docker/docker-compose.yml up -d

graph-down:
	@echo "Stopping Neo4j + Qdrant stack..."
	docker compose -f docker/docker-compose.yml down

backfill:
	@echo "Backfilling seed documents into Neo4j/Qdrant..."
	PYTHONPATH=src $(PYTHON) -m jobs.backfill_graph --pdf-dir data/seed --json-dir data/seed --report data/seed/backfill_report.csv

graph-validate:
	@echo "Validating Neo4j graph..."
	PYTHONPATH=src $(PYTHON) -m graph.validate_neo4j
	@echo "Validating Qdrant collections..."
	PYTHONPATH=src $(PYTHON) -m graph.validate_qdrant

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

# Structured knowledge base pipeline
kb-setup:
	@echo "Scanning knowledge base sources..."
	$(PYTHON) -m src.prep.kb_setup

kb-extract:
	@echo "Running OpenAI-powered structured extraction..."
	$(PYTHON) -m src.prep.kb_extract

kb-generate:
	@echo "Building disease markdown files..."
	$(PYTHON) -m src.prep.kb_generate

kb-validate:
	@echo "Validating structured knowledge output..."
	$(PYTHON) -m src.prep.kb_validate

kb-chunks:
	@echo "Inspecting chunk counts for structured knowledge base..."
	$(PYTHON) -m src.index.build_chunks

kb-embed:
	@echo "Creating embedding dump for structured knowledge base..."
	$(PYTHON) -m src.index.embed_index

kb-all: kb-setup kb-extract kb-generate kb-validate kb-embed
	@echo "Structured knowledge base pipeline completed."

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
