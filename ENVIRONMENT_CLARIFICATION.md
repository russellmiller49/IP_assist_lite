# Environment Clarification

## Current State (After Today's Work)

### Environment: `medparse-py311` (Python 3.11.13)

This single environment now contains **BOTH** projects installed in editable mode:

```
medparse-py311/
├── medparse (0.1.0)                    ← Subpackage from IP_assist_lite
│   └── /home/rjm/projects/IP_assist_lite
│
├── medparse-api (0.1.0)                ← From medparse-docling repo
│   └── /home/rjm/projects/ip_knowledge/medparse/medparse-docling
│
└── ip-assist-lite (0.1.0)              ← Main package from IP_assist_lite
    └── /home/rjm/projects/IP_assist_lite
```

### Repository Structure

**1. IP_assist_lite** (`/home/rjm/projects/IP_assist_lite`)
- **Package name**: `ip-assist-lite`
- **Python module**: `medparse` (the core extraction library)
- **Purpose**: RAG system with MedCPT embeddings, Qdrant, and GPT-5
- **Components**:
  - `medparse/` - Document extraction and normalization library
  - `src/` - RAG retrieval, LangGraph orchestration
  - `scripts/` - Utilities and tools

**2. medparse-docling** (`~/projects/ip_knowledge/medparse/medparse-docling`)
- **Package name**: `medparse-api`
- **Python module**: `medparse` (API wrapper around extraction)
- **Purpose**: FastAPI service for document extraction
- **Components**:
  - `medparse/` - Thin wrapper/extensions for docling
  - `api/` - FastAPI endpoints

### Import Behavior

When you run `import medparse` in the `medparse-py311` environment:

```python
import medparse  # This resolves to IP_assist_lite/medparse/ (first in sys.path)
```

The **IP_assist_lite version takes precedence** because:
1. Both are installed in editable mode (`pip install -e .`)
2. Python uses the first match in `sys.path`
3. `/home/rjm/projects/IP_assist_lite` appears before the medparse-docling path

### Recommendation: Separate Environments

To avoid confusion, I recommend creating dedicated environments:

#### Option A: Keep Current Setup (Simpler)
```bash
# Use medparse-py311 for both projects
# Just be aware that IP_assist_lite's medparse takes precedence
conda activate medparse-py311

# For IP_assist_lite work:
cd /home/rjm/projects/IP_assist_lite
python -m medparse.cli extract-articles ...

# For medparse-docling API work:
cd ~/projects/ip_knowledge/medparse/medparse-docling
# API endpoints call the same medparse extraction code
```

#### Option B: Separate Environments (Recommended for clarity)
```bash
# Create dedicated environment for medparse-docling
conda create -n medparse-docling-py311 python=3.11
conda activate medparse-docling-py311
cd ~/projects/ip_knowledge/medparse/medparse-docling
pip install -e .
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz

# Keep medparse-py311 for IP_assist_lite only
conda activate medparse-py311
cd /home/rjm/projects/IP_assist_lite
pip uninstall medparse-api  # Remove the docling version
```

#### Option C: Rename to Avoid Conflicts
The cleanest solution would be to rename one of the packages since both use `medparse` as the module name.

### Which Environment Should You Use?

**For today's work (IP_assist_lite extraction improvements):**
```bash
conda activate medparse-py311
cd /home/rjm/projects/IP_assist_lite
```

**All improvements we made today apply to**: IP_assist_lite's `medparse` module.

The medparse-docling API will benefit indirectly since it wraps the same extraction code, but you may need to sync the environment improvements there separately.

## Summary

- ✅ **medparse-py311 works for IP_assist_lite** (we tested UMLS linking successfully)
- ⚠️  **Both projects installed in same environment** (potential confusion)
- 🎯 **Today's work focused on**: IP_assist_lite's medparse extraction library
- 📝 **Recommendation**: Either separate the environments or be explicit about which project you're working on

---
*Created: 2025-10-28 after infrastructure improvements*
