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

## Technical Details

- **Models**: GPT-5 family with MedCPT embeddings
- **Database**: Qdrant vector store with hybrid retrieval
- **Safety**: Multi-layer safety checks and emergency detection
- **Performance**: Optimized for medical domain queries

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