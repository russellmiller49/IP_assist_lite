---
title: IP Assist Lite
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.44.1
app_file: app.py
pinned: false
license: mit
short_description: Medical Information Retrieval for Interventional Pulmonology
---

# 🏥 IP Assist Lite

**Medical Information Retrieval for Interventional Pulmonology**

## Features

- 🔍 **Hybrid Search**: MedCPT embeddings with BM25 and exact matching
- 📊 **Hierarchy-Aware Ranking**: Authority tiers (A1-A4) and evidence levels (H1-H4)
- 🚨 **Emergency Detection**: Automatic routing for urgent medical queries
- ⚠️ **Safety Checks**: Contraindication detection and pediatric warnings
- 📚 **Source Citations**: Confidence scoring with document authority

## Usage

This application provides AI-powered medical information retrieval specifically designed for interventional pulmonology. It can help with:

- Clinical decision support
- Procedure guidance
- CPT code lookup
- Contraindication checking
- Emergency protocol queries

## Important Notice

⚠️ **This system is for informational purposes only.** Always verify medical information with official guidelines and consult with qualified healthcare professionals before making clinical decisions.

## Authentication

This Space requires authentication. Please contact the administrator for access credentials.

## Project Structure

```
IP_assist_lite/
├── app.py                 # Main Gradio application
├── cli_interface.py       # Command-line interface
├── src/                   # Core source code
│   ├── llm/              # GPT-5 integration
│   ├── retrieval/        # Hybrid search implementation
│   ├── safety/           # Safety checks and contraindications
│   ├── prep/             # Data preparation pipelines
│   └── index/            # Embedding and indexing
├── data/                  # Processed data and embeddings
├── configs/               # Configuration files
├── scripts/               # Startup and utility scripts
├── documentation/         # User guides and project status
├── tests/                 # Test suites
└── bronchmonkey2/         # HuggingFace Spaces deployment (separate)

## Architecture Overview

IP Assist Lite is a sophisticated **medical RAG (Retrieval-Augmented Generation) system** built with **LangGraph 1.0** orchestration and medical domain-specific components.

### Core Technologies

- **🔄 LangGraph 1.0**: Workflow orchestration with state management
- **🧠 GPT-5 Family**: Language models for response synthesis
- **🔍 MedCPT**: Medical domain embeddings for semantic search
- **🗄️ Qdrant**: Vector database for hybrid retrieval
- **📊 BM25**: Sparse retrieval for exact matching
- **🛡️ Safety Guards**: Multi-layer medical safety checks

### System Architecture

```
Raw Medical Literature → Data Preparation → Chunking → Embedding → Indexing → Retrieval → LangGraph Orchestration → Response Synthesis → UI
```

## LangGraph Implementation

**Yes, this system extensively uses LangGraph 1.0** for intelligent query orchestration:

### Workflow Nodes
- **Query Classification**: Routes queries by type (clinical, procedure, coding, emergency, safety)
- **Information Retrieval**: Hybrid search with hierarchy-aware ranking
- **Response Synthesis**: GPT-5 powered generation with grounded citations
- **Safety Checks**: Multi-layer validation and warning systems

### State Management
- **AgentState**: Canonical state with medical-specific fields
- **Safety Flags**: Automatic detection of dosage, pediatric, contraindication queries
- **Emergency Routing**: Immediate handling of urgent medical queries
- **Confidence Scoring**: Authority-tiered response quality assessment

## Knowledge Base System

### Structured Knowledge (Not Traditional Knowledge Graphs)
- **Authority Tiers**: A1 (PAPOIP 2025) → A4 (case reports)
- **Evidence Levels**: H1 (systematic reviews) → H4 (expert opinion)
- **Domain Classification**: Medical domains (ablation, lung_volume_reduction, etc.)
- **Temporal Tracking**: Document validity periods and precedence scoring

### Data Sources
- **Medical Literature**: 500+ research papers, guidelines, textbooks
- **Clinical Guidelines**: PAPOIP 2025, Practical Guide 2022, BACADA 2012
- **Procedural Manuals**: Step-by-step technique descriptions
- **Coding References**: CPT/HCPCS codes and billing information

## Complete Data Pipeline

### Current Pipeline: PDF to Full Searchable System

The system now uses a streamlined pipeline that processes PDFs directly into a searchable medical information retrieval system:

#### 1. Start Graph Services
```bash
make graph-up
```
- **Starts**: Neo4j + Qdrant stack via Docker
- **Purpose**: Provides graph database and vector search infrastructure

#### 2. Ingest Documents
```bash
# For PDF files
ipa_ingest --path data/seed/*.pdf --doc-type auto

# For existing JSON payloads
ipa_ingest --json data/seed/*.json
```
- **Input**: PDF files or structured JSON documents
- **Process**: Extracts structured data via Medparse, persists to graph stores
- **Output**: Documents indexed in Neo4j graph and Qdrant vector database

#### 3. Validate Stores (Optional)
```bash
make graph-validate
```
- **Validates**: Neo4j graph structure and Qdrant collections
- **Purpose**: Ensures data integrity and proper indexing

#### 4. Launch Application
```bash
make ui
```
- **Starts**: Gradio interface for medical information retrieval
- **Features**: Hybrid search, authority-aware ranking, safety checks

### Legacy Pipeline (Deprecated)

The old pipeline (`make prep`, `make chunk`, `make embed`, `make index`) has been replaced by the streamlined ingestion process above.

### Pipeline Commands

```bash
# Complete current pipeline
make graph-up                    # Start services
ipa_ingest --path data/seed/*.pdf --doc-type auto  # Ingest documents
make graph-validate              # Validate stores (optional)
make ui                          # Launch application

# Service management
make graph-down                  # Stop graph services
make graph-validate              # Validate data stores

# Development helpers
make dev-prep                    # Process first 10 files (legacy)
make dev-chunk                   # Chunk first 5 documents (legacy)

# Statistics
make stats                       # Show pipeline statistics
make check-gpu                   # Verify GPU availability
```

## Running the Application

### Quick Start

```bash
# 1. Start graph services
make graph-up

# 2. Ingest your documents
ipa_ingest --path data/seed/*.pdf --doc-type auto

# 3. Launch the application
make ui
```

The application will be available at `http://localhost:7860`

### Alternative: Using Module Path

If `ipa_ingest` command is not available, use the module path:

```bash
# Ingest documents using module path
PYTHONPATH=src python -m jobs.ingest_documents --path data/seed/*.pdf --doc-type auto
```

**Note:** The main `app.py` now includes all enhanced features by default. The basic version is archived as `app_basic.py`.

## Features

The enhanced pipeline provides:
- **Query Assistant Tab:**
  - Multi-turn conversation support with context retention
  - Follow-up questions capability
  - Full AMA-style citations with journal details
  - Session management for continuous dialogue
  - Improved source tracking and confidence scoring
- **Procedural Coding Tab (V3):**
  - Automatic CPT/HCPCS code generation
  - EBUS station counting (31652 vs 31653)
  - NCCI conflict detection
  - Modifier recommendations
  - Billing guidance with documentation requirements
- **Enhanced Retrieval:**
  - Reranking for improved relevance
  - Authority-aware result ordering
  - Safety checks and contraindication warnings
  - Emergency query detection and routing

## Environment Variables

```bash
# Optional configuration
export IP_GPT5_MODEL=gpt-4o-mini  # or gpt-5-mini, gpt-5
export QDRANT_HOST=localhost
export QDRANT_PORT=6333
export MEDPARSE_URL=http://127.0.0.1:8099
export MEDPARSE_API_KEY=my-secret-medparse-key-123
```

## Troubleshooting

### Common Issues

1. **`ipa_ingest` command not found**
   ```bash
   # Use module path instead
   PYTHONPATH=src python -m jobs.ingest_documents --path data/seed/*.pdf --doc-type auto
   ```

2. **Graph services not starting**
   ```bash
   # Check Docker is running
   docker ps
   
   # Restart services
   make graph-down
   make graph-up
   ```

3. **Document ingestion fails**
   ```bash
   # Validate stores
   make graph-validate
   
   # Check service logs
   docker logs ip_assist_neo4j
   docker logs ip_assist_qdrant
   ```

## Technical Implementation Details

### LangGraph Workflow Architecture

The system uses **LangGraph 1.0** with a sophisticated state management system:

```python
# Core workflow nodes
classify_query → retrieve_information → synthesize_response → safety_check → end
```

**State Management:**
- **AgentState**: Canonical state with medical-specific fields
- **Safety Flags**: Automatic detection of critical medical terms
- **Emergency Routing**: Immediate handling of urgent queries
- **Confidence Scoring**: Authority-tiered response quality

### Hybrid Retrieval System

**Three-tier search approach:**
1. **MedCPT Semantic Search**: Medical domain embeddings for conceptual matching
2. **BM25 Sparse Retrieval**: Exact term matching for precise queries
3. **Hierarchy-Aware Ranking**: Authority tiers (A1-A4) and evidence levels (H1-H4)

**Retrieval Features:**
- Emergency detection and priority routing
- Contraindication and safety warnings
- CPT code exact matching
- Domain-specific filtering

### Medical Safety System

**Multi-layer safety checks:**
- **Query Classification**: Automatic detection of dosage, pediatric, contraindication queries
- **Response Validation**: Safety guard validation with warning generation
- **Emergency Routing**: Immediate handling of life-threatening scenarios
- **Review Flagging**: Automatic flagging of responses requiring medical review

### Data Processing Pipeline

**Input Requirements:**
- Raw medical literature in JSON format
- Clinical guidelines and procedural manuals
- CPT/HCPCS coding references
- Evidence-based medical content

**Processing Steps:**
1. **Standardization**: Clean and normalize medical text
2. **Metadata Extraction**: Authority tiers, evidence levels, domain classification
3. **Chunking**: Policy-driven semantic chunking with quality gates
4. **Embedding**: MedCPT medical domain embeddings
5. **Indexing**: Qdrant vector database with hierarchy-aware ranking

## System Requirements

### Hardware Requirements
- **GPU**: NVIDIA GPU recommended for MedCPT embedding generation
- **RAM**: 16GB+ recommended for large document processing
- **Storage**: 10GB+ for embeddings and vector database

### Software Dependencies
- **Python 3.8+**
- **LangGraph 1.0**: Workflow orchestration
- **Qdrant**: Vector database
- **MedCPT**: Medical domain embeddings
- **GPT-5 Family**: Language models
- **PyTorch**: GPU acceleration for embeddings

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm

# Verify GPU availability
python -c "import torch; print(f'GPU: {torch.cuda.is_available()}')"
```

## Development and Testing

### Development Commands
```bash
# Development mode (smaller datasets)
make dev-prep   # Process first 10 files
make dev-chunk  # Chunk first 5 documents

# Full pipeline
make all        # Complete data processing pipeline

# Individual components
make prep       # Data preparation
make chunk      # Chunking with quality gates
make embed      # MedCPT embedding generation
make index      # Qdrant indexing

# Testing and validation
make test       # Run test suite
make stats      # Show pipeline statistics
make check-gpu  # Verify GPU availability
```

### Quality Assurance
- **Chunk Quality Gates**: Automated validation of chunk quality
- **Safety Validation**: Multi-layer medical safety checks
- **Authority Ranking**: Evidence-based document precedence
- **Response Grounding**: Citations with confidence scoring

## About

IP Assist Lite is a **production-ready medical AI system** designed specifically for interventional pulmonology. It combines state-of-the-art RAG techniques with medical domain expertise, LangGraph orchestration, and comprehensive safety systems to provide reliable, evidence-based medical information retrieval.

**Key Differentiators:**
- Medical domain-specific embeddings (MedCPT)
- Hierarchy-aware authority ranking
- Multi-layer safety validation
- LangGraph workflow orchestration
- Evidence-based response generation
- Comprehensive medical literature coverage
