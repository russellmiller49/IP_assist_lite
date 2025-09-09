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

```bash
# Start Qdrant database
./scripts/start_qdrant_local.sh

# Run the Gradio app
python app.py

# Or use the Makefile
make all  # Run complete pipeline
```