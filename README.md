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

### From Raw Data to Final App

The system processes medical literature through a comprehensive pipeline:

#### 1. Data Preparation (`make prep`)
```bash
src/prep/data_preparer_v12.py
```
- **Input**: Raw JSON files from medical literature (~500+ documents)
- **Process**: Standardization, cleaning, metadata extraction
- **Output**: Processed documents with authority tiers (A1-A4), evidence levels (H1-H4), domain classification

#### 2. Chunking (`make chunk`)
```bash
src/index/chunker_v2.py
```
- **Input**: Processed documents
- **Process**: Policy-driven chunking with quality gates
- **Output**: Semantic chunks with precedence scoring and medical domain tags

#### 3. Embedding Generation (`make embed`)
```bash
src/index/embed_medcpt.py
```
- **Input**: Chunks
- **Process**: MedCPT embeddings (medical domain-specific)
- **Output**: Vector embeddings optimized for medical terminology

#### 4. Indexing (`make index`)
```bash
src/index/upsert_qdrant.py
```
- **Input**: Embeddings + metadata
- **Process**: Qdrant vector database indexing
- **Output**: Searchable vector index with hierarchy-aware ranking

#### 5. Hybrid Retrieval System
```bash
src/retrieval/hybrid_retriever.py
```
- **MedCPT Semantic Search**: Medical domain embeddings
- **BM25 Sparse Retrieval**: Exact term matching
- **Hierarchy-Aware Ranking**: Authority tiers and evidence levels
- **Safety Checks**: Emergency detection, contraindication warnings

#### 6. LangGraph Orchestration
```bash
src/orchestration/langgraph_agent.py
```
- **Query Classification**: Clinical, procedure, coding, emergency, safety
- **Intelligent Routing**: Based on query type and safety flags
- **Response Synthesis**: GPT-5 powered with grounded generation
- **Safety Validation**: Multi-layer medical safety checks

#### 7. User Interface
```bash
app.py (Gradio)
```
- **Multi-turn Conversations**: Context retention across queries
- **AMA Citations**: Full journal references with authority tiers
- **Procedural Coding**: V3 CPT code generation with NCCI checks
- **Safety Warnings**: Automatic flagging of critical information

### Pipeline Commands

```bash
# Complete pipeline
make all  # prep → chunk → embed → index

# Individual steps
make prep    # Process raw medical literature
make chunk   # Create semantic chunks
make embed   # Generate MedCPT embeddings
make index   # Build Qdrant index

# Development mode
make dev-prep   # Process first 10 files
make dev-chunk  # Chunk first 5 documents

# Statistics
make stats      # Show pipeline statistics
make check-gpu  # Verify GPU availability
```

## Running the Application

**Note:** The main `app.py` now includes all enhanced features by default. The basic version is archived as `app_basic.py`.

### Standard Pipeline (Now Enhanced)
```bash
# 1. Start Qdrant database
./scripts/start_qdrant_local.sh

# 2. Run the main app (includes all enhanced features)
python app.py

# Or use the Makefile
make all  # Run complete pipeline
```

**Features included:**
- 💬 Multi-turn conversation support
- 📚 Full AMA format citations
- 📋 V3 Procedural Coding with Q&A
- 🔍 Enhanced retrieval with reranking

### Alternative Options
```bash
# Run the basic/legacy version (without enhancements)
python app_basic.py

# Run with specific port
GRADIO_SERVER_PORT=7861 python app.py

# Use the CLI interface
python cli_enhanced.py

# Set environment variables (optional)
export IP_GPT5_MODEL=gpt-4o-mini  # or gpt-5-mini, gpt-5
export QDRANT_HOST=localhost
export QDRANT_PORT=6333
```

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
  - TBLB lobe tracking with add-on codes
  - Sedation time calculation and family selection
  - NCCI edit checks and warnings
  - OPPS packaging notes
  - ICD-10-PCS suggestions
  - Documentation gap detection

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