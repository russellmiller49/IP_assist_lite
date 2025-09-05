# IP Assist Lite - Medical Information Retrieval System

A high-performance medical information retrieval system specialized for Interventional Pulmonology, using MedCPT dual encoders, hybrid search, and hierarchy-aware ranking with LangGraph 1.0 orchestration.

## Features

- **Dense Retrieval**: MedCPT dual encoders on GPU (Article → chunks, Query → queries)
- **Sparse Retrieval**: BM25 union for exact medical terms and CPT/wRVU codes
- **Exact-Match Hooks**: Direct lookup by CPT code and device brand aliases
- **Reranking**: GPU cross-encoder on top-K results
- **Hierarchy-Aware Ranking**: Authority tiers (A1>A2>A3>A4) with domain-aware recency
- **Safety Layer**: Rule-first contraindications, dose/energy validation, emergency routing
- **Smart Chunking**: Variable size by section type (procedures intact, tables row-level)
- **LangGraph 1.0**: Modern graph-based orchestration with emergency fast paths

## Quick Start

### Prerequisites

- WSL2 with Ubuntu 22.04 (or native Linux)
- NVIDIA GPU with CUDA support (tested on 4070 Ti)
- Conda/Miniconda installed
- Docker (for Qdrant vector database)

### Installation

1. Clone the repository and navigate to it:
```bash
cd /home/rjm/projects/IP_assist_lite
```

2. Activate conda environment:
```bash
conda activate ipass2
```

3. Install dependencies:
```bash
make setup
```

4. Start Qdrant vector database:
```bash
make docker-up
```

### Running the Pipeline

Process the complete pipeline:
```bash
make all
```

Or run individual steps:

1. **Data Preparation** - Standardize and clean documents:
```bash
make prep
```

2. **Chunking** - Create variable-sized chunks:
```bash
make chunk
```

3. **Embedding** - Generate MedCPT embeddings (requires GPU):
```bash
make embed
```

4. **Indexing** - Build Qdrant index:
```bash
make index
```

5. **Start API**:
```bash
make api
```

6. **Start UI**:
```bash
make ui
```

## Architecture

### Data Flow

```
Raw JSON → Prep (clean/standardize) → Chunk (variable) → Embed (MedCPT) → Index (Qdrant)
                                                                              ↓
Query → LangGraph Orchestrator → Hybrid Retrieval → Rerank → Safety Check → Answer
```

### Knowledge Hierarchy

- **Authority Tiers**: A1 (PAPOIP 2025) > A2 (Practical Guide) > A3 (BACADA) > A4 (Articles)
- **Evidence Levels**: H1 (Guidelines/SR) > H2 (RCT) > H3 (Cohort) > H4 (Case)
- **Domain-Aware Recency**: Coding (3yr), Ablation (5yr), Clinical (6yr) half-lives

### Key Components

- `src/ip_assistant/utils/clean.py` - Robust text cleaning (ligatures, artifacts)
- `src/prep/data_preparer_v12.py` - Document standardization with metadata
- `src/index/chunk.py` - Variable chunking by section type
- `src/extract/critical_numbers.py` - Extract CPT, devices, complications
- `src/index/embed_medcpt.py` - GPU-optimized MedCPT embeddings
- `src/orchestrator/flow.py` - LangGraph 1.0 retrieval pipeline
- `src/safety/guards.py` - Safety validation and contraindications

## API Endpoints

- `POST /query` - Main query endpoint
- `GET /health` - Health check
- `GET /sources` - List available sources
- `POST /feedback` - Submit feedback

## Configuration

Key configuration files in `configs/`:
- `ranking.yaml` - Weights and domain half-lives
- `chunking.yaml` - Section-specific chunk policies
- `safety.yaml` - Contraindications and dose validation
- `terminology.yaml` - Aliases and normalization

## Testing

Run tests:
```bash
make test
```

Check GPU availability:
```bash
make check-gpu
```

View statistics:
```bash
make stats
```

## Emergency Handling

The system includes fast-path routing for emergency queries:
- Massive hemoptysis (>200ml, hemodynamic instability)
- Foreign body aspiration
- Tension pneumothorax

Emergency responses bypass normal retrieval for <500ms latency.

## Development

For development with smaller datasets:
```bash
make dev-prep   # Process first 10 files
make dev-chunk  # Chunk first 5 documents
```

## Memory Management

WSL users should configure memory limits in `.wslconfig`:
```ini
[wsl2]
memory=32GB
processors=8
swap=8GB
```

## License

Proprietary - Medical Information System

## Support

For issues or questions, please contact the development team.