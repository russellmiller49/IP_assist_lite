# IP Assist Lite - Project Status and Roadmap

## Project Overview
A high-performance medical information retrieval system for Interventional Pulmonology using MedCPT embeddings, hybrid search, and hierarchy-aware ranking with LangGraph 1.0 orchestration.

## ✅ Completed Components (Phase 1)

### 1. Core Infrastructure
- [x] **Project Structure**: Complete directory layout with separation of concerns
- [x] **Conda Environment**: Using `ipass2` environment  
- [x] **Requirements File**: All dependencies specified including LangGraph 1.0 alpha
- [x] **Makefile**: Automated pipeline execution commands
- [x] **Docker Setup**: Qdrant vector database configuration

### 2. Data Processing Pipeline
- [x] **Text Cleaner** (`src/ip_assistant/utils/clean.py`)
  - Ligature removal (fi, fl, ffi, ffl)
  - Publisher artifact cleaning (/uniFB01, /C21, etc.)
  - Double expansion collapse (e.g., "EBUS (EBUS)")
  - Unicode normalization

- [x] **Data Preparer v1.2** (`src/prep/data_preparer_v12.py`)
  - Authority tier assignment (A1-A4)
  - Evidence level determination (H1-H4)
  - Domain classification (clinical, coding_billing, ablation, etc.)
  - Table promotion to Markdown + structured format
  - Temporal validity tracking
  - Alias extraction
  - Domain-aware precedence calculation with A1 floor

- [x] **Variable Chunking System** (`src/index/chunk.py`)
  - Section-aware chunking:
    - Procedures: ≤800 tokens intact
    - Complications/coding: 300-450 tokens
    - Ablation/BLVR: 350-500 tokens
    - General: 400-600 tokens
  - Row-level table chunks
  - CPT code and alias indexing

### 3. Information Extraction
- [x] **Critical Number Extractor** (`src/extract/critical_numbers.py`)
  - CPT codes and wRVU values
  - Device brands (Zephyr, Spiration, Chartis)
  - Energy settings and ablation parameters
  - Complication rates and percentages
  - Equipment specifications
  - Fiducial marker requirements
  - Training requirements
  - BLVR eligibility criteria

- [x] **Contraindication Extractor** (`src/extract/contraindications.py`)
  - Absolute/relative/caution classification
  - Condition-specific patterns
  - Procedure-specific contraindications
  - Context extraction

### 4. Embedding & Indexing
- [x] **MedCPT Embedder** (`src/index/embed_medcpt.py`)
  - GPU batch optimization
  - Adaptive batch sizing based on VRAM
  - Article and query encoder support
  - Memory-efficient processing

- [x] **Batch Optimizer** (`src/index/emb_batch.py`)
  - Dynamic batch size calculation
  - VRAM detection (optimized for 4070 Ti)
  - OOM prevention

- [x] **Qdrant Indexer** (`src/index/upsert_qdrant.py`)
  - Collection management
  - Batch uploading
  - Metadata filtering support
  - Search with domain/year/tier filters

### 5. Orchestration
- [x] **LangGraph 1.0 Flow** (`src/orchestrator/flow.py`)
  - Graph-based pipeline with conditional edges
  - Query classification (emergency, coding, clinical, safety)
  - Emergency fast-path routing (<500ms)
  - Parallel retrieval (BM25, dense, exact-match)
  - State management with TypedDict
  - Predefined emergency protocols

### 6. Documentation & Testing
- [x] **README.md**: Complete usage guide
- [x] **Docker Compose**: Qdrant configuration
- [x] **Test System Script**: Verification of setup
- [x] **Makefile Commands**: Automated pipeline

## 🚧 Pending Components (Phase 2)

### 1. Retrieval System
- [ ] **BM25 Implementation** (`src/retrieve/bm25.py`)
  - Whitespace tokenization
  - Index building from chunks
  - Query expansion with aliases

- [ ] **Dense Retrieval** (`src/retrieve/dense.py`)
  - MedCPT query encoder integration
  - Qdrant query interface
  - Top-K retrieval

- [ ] **Exact Match Fusion** (`src/retrieve/exact_match.py`)
  - CPT code lookup from term index
  - Device alias matching
  - Score boosting for exact matches

- [ ] **Result Merger** (`src/retrieve/merge.py`)
  - De-duplication logic
  - Score normalization
  - Hybrid score calculation

### 2. Ranking & Scoring
- [ ] **Hierarchy-Aware Scorer** (`src/retrieve/score.py`)
  - Precedence calculation (0.45*precedence + 0.35*semantic + 0.10*section + 0.10*entity)
  - Domain-specific boosts
  - Exact-match bonuses

- [ ] **Cross-Encoder Reranker** (`src/retrieve/rerank.py`)
  - MedCPT or MiniLM cross-encoder
  - Top-30 reranking
  - GPU acceleration

- [ ] **Conflict Resolver** (`src/retrieve/conflict.py`)
  - Standard of care guard (A1 protection)
  - COVID/pediatric exceptions
  - Recency-based override logic

### 3. Safety Layer
- [ ] **Safety Guards** (`src/safety/guards.py`)
  - Contraindication checking
  - Dose validation (≥2 sources, ±20% variance)
  - Pediatric dose flagging
  - Emergency technique marking

- [ ] **Configuration Files**
  - `configs/safety.yaml`: Critical procedures, dose validation rules
  - `configs/ranking.yaml`: Weights and half-lives
  - `configs/chunking.yaml`: Section-specific policies
  - `configs/terminology.yaml`: Alias mappings

### 4. API & UI
- [ ] **FastAPI Endpoints** (`src/api/main.py`)
  - POST /query - Main retrieval endpoint
  - GET /health - Health check
  - GET /sources - Document registry
  - POST /feedback - User feedback

- [ ] **Gradio Interface** (`src/ui/app.py`)
  - Chat interface
  - Source viewer
  - CPT/wRVU table display
  - Temporal validity warnings
  - Risk Box for emergencies

### 5. Testing Suite
- [ ] **Retrieval Tests** (`tests/test_retrieval.py`)
  - Recall@5 ≥ 0.8 on gold queries
  - MRR@10 improvement with reranking
  - CPT exact-match validation

- [ ] **Safety Tests** (`tests/test_safety.py`)
  - Zero missed contraindications
  - Dose validation accuracy
  - Emergency routing latency

- [ ] **Critical Cases** (`tests/test_critical.py`)
  - SEMS benign stenosis warning
  - Fiducial placement requirements (3-6 markers, 1.5-5cm, non-collinear)
  - MT competency (20 supervised + 10/year)
  - COVID PDT adaptations

## 📊 Data Statistics
- **Raw Files**: 460 JSON documents (3 books + articles)
- **Domains**: clinical, coding_billing, ablation, lung_volume_reduction, technology_navigation
- **Authority Tiers**: A1 (PAPOIP 2025), A2 (Practical Guide), A3 (BACADA), A4 (Articles)
- **Processing Status**: Ready for full pipeline execution

## 🚀 Next Steps to Complete System

### Immediate Actions (Do These First)
1. **Install Dependencies**
   ```bash
   conda activate ipass2
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```

2. **Process Initial Data**
   ```bash
   make prep   # ~10-15 minutes for 460 files
   make chunk  # ~5 minutes
   ```

3. **Generate Embeddings** (Requires GPU)
   ```bash
   make embed  # ~20-30 minutes on 4070 Ti
   ```

4. **Setup Vector Database**
   ```bash
   make docker-up
   make index
   ```

### Development Priority Order
1. **Week 1**: Complete retrieval components (BM25, dense, merge)
2. **Week 2**: Implement ranking and conflict resolution
3. **Week 3**: Add safety layer and configuration
4. **Week 4**: Build API and UI
5. **Week 5**: Create comprehensive test suite
6. **Week 6**: Performance optimization and caching

## 🎯 Success Metrics
- **Latency**: P95 < 1.5s, emergency < 500ms
- **Accuracy**: Recall@5 ≥ 0.8, zero critical safety misses
- **Coverage**: >80% chunks yield extractable information
- **Safety**: 100% contraindication detection, ≥2 source dose validation

## 💡 Technical Decisions Made
1. **LangGraph 1.0 alpha** for orchestration (graph-based, clean separation)
2. **MedCPT** over general embeddings (medical-specific)
3. **Variable chunking** over fixed size (preserve procedure integrity)
4. **Hierarchy-aware ranking** over simple similarity (medical authority matters)
5. **Row-level table chunks** for precise CPT/wRVU retrieval
6. **Emergency fast-path** for critical situations

## 📝 Notes for Resumption
- The system is architecturally complete but needs retrieval and API implementation
- All complex logic (chunking, extraction, embedding) is done
- Focus should be on connecting the pieces and building the retrieval layer
- Consider using async for all I/O operations to improve performance
- The Makefile provides good entry points for testing each component

## 🐛 Known Issues
- Dependencies not installed in conda environment yet
- No actual retrieval happening (placeholders in orchestrator)
- API/UI not implemented
- Test data needs to be created for validation

## 📚 Resources
- [LangGraph 1.0 Docs](https://python.langchain.com/docs/langgraph)
- [MedCPT Paper](https://arxiv.org/abs/2212.13391)
- [Qdrant Documentation](https://qdrant.tech/documentation/)

---
*Last Updated: 2025-01-09*
*Status: Phase 1 Complete, Ready for Phase 2 Implementation*