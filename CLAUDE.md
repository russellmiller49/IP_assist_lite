# Claude Instructions for IP Assist Lite

## Project Context
You are working on IP Assist Lite, a medical information retrieval system for Interventional Pulmonology. The system uses MedCPT embeddings, hybrid search, and hierarchy-aware ranking to provide accurate medical information from authoritative sources.

## Key Architecture Decisions

### 1. Knowledge Hierarchy
- **Authority Tiers**: A1 (PAPOIP 2025) > A2 (Practical Guide 2022) > A3 (BACADA 2012) > A4 (Articles)
- **Evidence Levels**: H1 (Guidelines/SR) > H2 (RCT) > H3 (Cohort/Coding) > H4 (Case)
- **A1 Floor**: A1 documents maintain minimum 70% recency weight
- **Standard of Care Guard**: A1 not superseded by A4 unless H1/H2 with ≥3 year advantage

### 2. Domain-Aware Processing
Domains affect recency half-lives and processing:
- `coding_billing`: 3-year half-life, H3 default, warn if ≥4 years old
- `ablation`: 5-year half-life
- `technology_navigation`: 4-year half-life  
- `clinical`: 6-year half-life (default)

### 3. Variable Chunking Strategy
Section-aware chunking (NEVER use fixed sizes):
- **Procedures**: Keep intact up to 800 tokens (preserve numbered steps)
- **Tables**: Row-level chunks + full table chunk
- **Complications/Coding**: 300-450 tokens
- **Ablation/BLVR**: 350-500 tokens
- **General**: 400-600 tokens

### 4. Critical Information Extraction
Always extract:
- CPT codes (5-digit patterns)
- wRVU values (relative value units)
- Device brands (Zephyr, Spiration, Chartis)
- Complication rates (% with context)
- Energy settings (watts, temperature)
- Contraindications (absolute/relative/caution)

## Environment Setup

### Conda Environment
```bash
conda activate ipass2  # ALWAYS use this environment
```

### GPU Optimization
- Batch size 256 for 12GB VRAM (4070 Ti)
- Use adaptive batch sizing to prevent OOM
- Clear CUDA cache periodically

### File Locations
- Raw data: `data/raw/*.json`
- Processed: `data/processed/*.json`
- Chunks: `data/chunks/chunks.jsonl`
- Embeddings: `data/vectors/*.npy`
- Term indexes: `data/term_index/{cpt,aliases}.jsonl`

## Code Style Guidelines

### Text Processing
- ALWAYS call `normalize_text()` before any text processing
- Remove ligatures (/uniFB01 → fi)
- Collapse double expansions ("EBUS (EBUS)" → "EBUS")
- Clean table cells separately with `clean_table_cell()`

### Error Handling
- Use try/except for file operations
- Continue processing on single file errors
- Log warnings for outdated coding content
- Validate CPT codes (5 digits, numeric)

### Performance
- Process in batches when possible
- Use numpy arrays for embeddings
- Implement caching for expensive operations
- Prefer async for I/O operations

## Testing Requirements

### Retrieval Metrics
- Recall@5 ≥ 0.8 on gold queries
- MRR@10 improvement with reranking
- CPT exact-match in top-5 when queried

### Safety Validation
- Zero missed contraindications
- Dose/settings require ≥2 sources
- Flag pediatric doses
- Emergency response < 500ms

### Critical Test Cases
1. **Fiducials**: Must return "3-6 markers, 1.5-5cm apart, non-collinear" (A1)
2. **MT Competency**: Must return "20 supervised, 10/year maintenance" (A2)
3. **SEMS Benign**: Must warn "contraindicated in resectable disease" (A3)
4. **COVID PDT**: Must mention "scope alongside ETT" (A4)

## Common Commands

### Pipeline Execution
```bash
make prep      # Process documents
make chunk     # Create chunks
make embed     # Generate embeddings (GPU)
make index     # Build Qdrant index
make all       # Run complete pipeline
```

### Development
```bash
make dev-prep   # Process first 10 files
make dev-chunk  # Chunk first 5 documents
make stats      # View statistics
make test       # Run tests
```

### Docker
```bash
make docker-up   # Start Qdrant
make docker-down # Stop Qdrant
```

## Important Patterns

### Precedence Calculation
```python
precedence = 0.5*recency + 0.3*H_weight + 0.2*A_weight
```

### Final Score
```python
score = 0.45*precedence + 0.35*semantic + 0.10*section + 0.10*entity + bonuses
```

### Emergency Detection
Check for: "massive hemoptysis", ">200ml", "foreign body", "tension pneumothorax"

## LangGraph 1.0 Integration
- Use StateGraph with TypedDict for state management
- Implement conditional edges for emergency routing
- Keep nodes focused (single responsibility)
- Use async for all node functions

## Safety First
- NEVER skip contraindication checks
- ALWAYS validate doses against multiple sources
- FLAG any pediatric considerations
- ROUTE emergencies immediately (bypass normal flow)

## Debugging Tips
1. Check GPU memory: `nvidia-smi`
2. Verify Qdrant: `curl localhost:6333/health`
3. Test imports: `python test_system.py`
4. View logs: Check Makefile output
5. Count chunks: `wc -l data/chunks/chunks.jsonl`

## Project Philosophy
"Accuracy over speed, except in emergencies. Authority matters. Recent coding updates override old ones. Keep procedures intact. Tables are first-class citizens. Safety gates are non-negotiable."

---
*Remember: This is a medical system. Errors have consequences. When in doubt, be conservative and flag for review.*