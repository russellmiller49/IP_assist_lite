# Hugging Face Spaces Upload Guide - Full Functionality

## Complete Folder Structure for HF Spaces

```
your-space/
├── app.py                          # Main application (renamed from app_hf_spaces_zerogpu.py)
├── requirements.txt                # Dependencies (renamed from requirements_zerogpu.txt)
├── README.md                       # Space README with YAML frontmatter
├── .gitignore                      # Ignore unnecessary files
├── .gitattributes                  # LFS tracking for large files
│
├── src/                            # Source code modules
│   ├── __init__.py
│   ├── llm/
│   │   ├── __init__.py
│   │   └── gpt5_medical.py        # GPT-5 wrapper with fallback
│   ├── retrieval/
│   │   ├── __init__.py
│   │   └── hybrid_retriever.py    # If using modular approach
│   └── utils/
│       ├── __init__.py
│       └── serialization.py       # JSON serialization helpers
│
├── data/                           # Preprocessed data files
│   ├── chunks/
│   │   └── chunks.jsonl           # Document chunks (required)
│   ├── vectors/
│   │   └── embeddings.npy         # Precomputed embeddings (optional but recommended)
│   ├── term_index/
│   │   ├── cpt.jsonl             # CPT code index
│   │   └── aliases.jsonl         # Medical term aliases
│   └── processed/
│       └── *.json                # Processed documents (optional)
│
├── cache/                         # Runtime cache (created automatically)
│   ├── embeddings.pkl
│   └── index.pkl
│
└── utils/                         # Utility scripts (optional)
    └── serialization.py

```

## Essential Files to Upload

### 1. Core Application Files (REQUIRED)

```bash
# Rename and prepare main files
cp app_hf_spaces_zerogpu.py app.py
cp requirements_zerogpu.txt requirements.txt
```

### 2. Data Files for Full Functionality (REQUIRED)

#### a. Document Chunks File (`data/chunks/chunks.jsonl`)
This is the most important data file. Each line should be a JSON object:

```json
{"chunk_id": "doc1_chunk_001", "text": "Bronchoscopy contraindications include...", "doc_id": "PAPOIP_2025", "doc_type": "guidelines", "section_title": "Contraindications", "year": 2025, "authority_tier": "A1", "evidence_level": "H1", "domain": "clinical", "cpt_codes": ["31622"], "keywords": ["bronchoscopy", "contraindications"]}
{"chunk_id": "doc1_chunk_002", "text": "Massive hemoptysis management requires...", "doc_id": "Emergency_Protocols", "doc_type": "protocol", "section_title": "Emergency", "year": 2024, "authority_tier": "A1", "evidence_level": "H1", "domain": "clinical", "cpt_codes": ["31645"], "keywords": ["hemoptysis", "emergency"]}
```

#### b. Embeddings File (`data/vectors/embeddings.npy`) - RECOMMENDED
Precomputed embeddings for faster search:
```python
# Generate this file locally before upload
import numpy as np
from sentence_transformers import SentenceTransformer
import jsonlines

# Load chunks
chunks = []
with jsonlines.open('data/chunks/chunks.jsonl') as reader:
    chunks = list(reader)

# Generate embeddings
model = SentenceTransformer('chrisjay/MedCPT-Query-Encoder')
texts = [chunk['text'] for chunk in chunks]
embeddings = model.encode(texts, batch_size=32, show_progress_bar=True)

# Save
np.save('data/vectors/embeddings.npy', embeddings)
```

#### c. CPT Index File (`data/term_index/cpt.jsonl`) - RECOMMENDED
Index mapping CPT codes to chunk IDs:
```json
{"cpt_code": "31622", "chunk_ids": ["doc1_chunk_001", "doc2_chunk_045"]}
{"cpt_code": "31633", "chunk_ids": ["doc3_chunk_012", "doc4_chunk_089"]}
```

### 3. Supporting Python Modules (OPTIONAL but recommended for modularity)

Create `src/utils/serialization.py`:
```python
"""JSON serialization utilities"""
from typing import Any
import json
import numpy as np

def to_jsonable(obj: Any) -> Any:
    """Convert objects to JSON-serializable format"""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    elif hasattr(obj, 'model_dump'):
        return obj.model_dump()
    elif hasattr(obj, '__dict__'):
        return {k: to_jsonable(v) for k, v in obj.__dict__.items() 
                if not k.startswith('_')}
    elif isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [to_jsonable(item) for item in obj]
    else:
        return obj
```

## Step-by-Step Upload Process

### Method 1: Via Git (Recommended for Large Files)

```bash
# 1. Clone your space
git clone https://huggingface.co/spaces/YOUR_USERNAME/ip-assist-lite
cd ip-assist-lite

# 2. Set up Git LFS for large files
git lfs install
git lfs track "*.npy"
git lfs track "*.pkl"
git lfs track "*.jsonl"

# 3. Create directory structure
mkdir -p data/chunks data/vectors data/term_index src/utils cache

# 4. Copy application files
cp /path/to/app_hf_spaces_zerogpu.py app.py
cp /path/to/requirements_zerogpu.txt requirements.txt

# 5. Copy data files
cp /path/to/chunks.jsonl data/chunks/
cp /path/to/embeddings.npy data/vectors/
cp /path/to/cpt.jsonl data/term_index/

# 6. Copy source modules (if using modular approach)
cp /path/to/src/utils/serialization.py src/utils/
touch src/__init__.py
touch src/utils/__init__.py

# 7. Create README with YAML frontmatter
cat > README.md << 'EOF'
---
title: IP Assist Lite Medical AI
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: apache-2.0
---

# IP Assist Lite
Medical AI for Interventional Pulmonology
EOF

# 8. Create .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
.env
*.log
.DS_Store
EOF

# 9. Commit and push
git add .
git commit -m "Complete deployment with data files"
git push
```

### Method 2: Via HF Web Interface

1. **Navigate to Files tab** in your Space
2. **Create folders** using "Add file" > "Create a new file":
   - Create `data/chunks/dummy.txt` (then delete dummy.txt)
   - Create `data/vectors/dummy.txt`
   - Create `data/term_index/dummy.txt`

3. **Upload files in order**:
   - First: `app.py`, `requirements.txt`, `README.md`
   - Then: `data/chunks/chunks.jsonl`
   - Then: `data/vectors/embeddings.npy` (if < 25MB)
   - Then: `data/term_index/cpt.jsonl`

### Method 3: Hybrid Approach (Best for Large Embeddings)

```bash
# Upload small files via web UI
# Upload large files via Git LFS

# For embeddings.npy > 25MB:
git clone https://huggingface.co/spaces/YOUR_USERNAME/ip-assist-lite
cd ip-assist-lite
git lfs track "*.npy"
cp /path/to/embeddings.npy data/vectors/
git add data/vectors/embeddings.npy
git commit -m "Add embeddings via LFS"
git push
```

## Generating Required Data Files

### From Your Existing Project

```bash
# In your local project with conda env
conda activate ipass2

# Run the processing pipeline
make prep      # Process raw documents
make chunk     # Create chunks.jsonl
make embed     # Generate embeddings.npy
make index     # Create term indices

# Files will be in:
# - data/chunks/chunks.jsonl
# - data/vectors/embeddings.npy
# - data/term_index/cpt.jsonl
```

### Creating Minimal Test Data

If you want to test without full data, create minimal files:

`data/chunks/chunks.jsonl`:
```json
{"chunk_id": "test_001", "text": "Bronchoscopy is a procedure to look inside the airways", "doc_id": "test_doc", "doc_type": "guidelines", "section_title": "Overview", "year": 2024, "authority_tier": "A1", "evidence_level": "H1", "domain": "clinical", "cpt_codes": ["31622"], "keywords": ["bronchoscopy"]}
{"chunk_id": "test_002", "text": "EBUS-TBNA is used for lymph node sampling", "doc_id": "test_doc", "doc_type": "guidelines", "section_title": "Procedures", "year": 2024, "authority_tier": "A1", "evidence_level": "H1", "domain": "clinical", "cpt_codes": ["31633"], "keywords": ["EBUS", "TBNA"]}
```

## Environment Variables Setup

In your HF Space Settings > Variables and secrets:

### Required Secrets:
```
OPENAI_API_KEY=sk-...your_key...
IP_GPT5_MODEL=gpt-5-mini
```

### Optional Secrets:
```
HF_USERNAME=admin
HF_PASSWORD=secure_password_here
EMBEDDING_MODEL=chrisjay/MedCPT-Query-Encoder
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

## Verification Checklist

After uploading, verify:

- [ ] `app.py` exists in root
- [ ] `requirements.txt` exists in root
- [ ] `README.md` has YAML frontmatter
- [ ] `data/chunks/chunks.jsonl` exists and has content
- [ ] Environment variables are set in Space settings
- [ ] Build completes without errors
- [ ] Space loads without errors
- [ ] Test queries return responses

## Troubleshooting

### If embeddings.npy is missing:
The app will fall back to generating embeddings on-the-fly (slower but functional)

### If chunks.jsonl is missing:
The app will use mock data (limited functionality)

### For large files (>25MB):
Must use Git LFS:
```bash
git lfs track "*.npy"
git add .gitattributes
git add large_file.npy
git commit -m "Add large file via LFS"
git push
```

### Memory issues:
Reduce the number of chunks or embedding dimensions

## Performance Tips

1. **Precompute embeddings** locally and upload to avoid GPU computation
2. **Use smaller chunks** (400-600 tokens) for better retrieval
3. **Index CPT codes** for fast medical code lookup
4. **Enable caching** (already in code) for repeated queries
5. **Use ZeroGPU** hardware tier for best performance

## Data Quality Guidelines

For best results, ensure your `chunks.jsonl` has:
- Accurate `authority_tier` (A1-A4) classifications
- Correct `evidence_level` (H1-H4) assignments
- Recent `year` values for time-sensitive content
- Complete `cpt_codes` arrays where applicable
- Relevant `keywords` for better BM25 matching

---

**Note**: The app will work with just `app.py` and `requirements.txt` using mock data, but full functionality requires at least the `chunks.jsonl` file.