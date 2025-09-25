# IP Assist Lite - Clean Repository

This is a clean version of IP Assist Lite designed for building fresh knowledge bases with different medical specialties or domains.

## What's Included

- **Core Application**: Complete IP Assist Lite application
- **Medparse Integration**: Ready-to-use medical text processing API
- **Configuration Templates**: Ready-to-customize configs
- **Deployment Scripts**: HuggingFace Spaces deployment ready

## What's Removed

- Specific knowledge base data (articles, textbooks)
- Chat transcripts and notes
- Test outputs and logs
- Generated documentation

## Quick Start

### 1. Setup Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables
export OPENAI_API_KEY="your-openai-key"
export UMLS_API_KEY="your-umls-key"  # Optional
export NCBI_API_KEY="your-ncbi-key"  # Optional
```

### 2. Start Medparse API

```bash
cd ../ip_knowledge/medparse/medparse-docling
uvicorn api.main:app --reload --port 8099
```

### 3. Start IP Assist Lite

```bash
./run.sh
```

## Building a Fresh Knowledge Base

### Step 1: Prepare Your Documents

1. **PDFs**: Place your medical articles/textbooks in `data/raw_pdfs/`
2. **Text Files**: Place any text documents in `data/raw_text/`

### Step 2: Process Documents

```bash
# Process PDFs through medparse
python scripts/process_pdfs.py

# Extract and chunk text
python scripts/extract_text.py

# Build knowledge base
python scripts/build_knowledge_base.py
```

### Step 3: Configure Retrieval

Edit `configs/retrieval_config.yaml` to customize:
- Chunk sizes
- Overlap settings
- Embedding models
- Retrieval strategies

### Step 4: Test Your Knowledge Base

```bash
# Test retrieval
python scripts/test_retrieval.py

# Run the application
./run.sh
```

## Customization Options

### Medical Specialties
- **Pulmonology**: Focus on lung procedures
- **Cardiology**: Heart and vascular procedures  
- **Gastroenterology**: Digestive system procedures
- **Urology**: Urinary system procedures

### Knowledge Sources
- **Textbooks**: Comprehensive medical textbooks
- **Journals**: Recent research articles
- **Guidelines**: Clinical practice guidelines
- **Procedural Manuals**: Step-by-step procedure guides

## Configuration Files

- `configs/retrieval_config.yaml` - Retrieval settings
- `configs/llm_config.yaml` - LLM model settings
- `configs/medparse_config.yaml` - Medparse API settings

## Deployment

### HuggingFace Spaces
```bash
cd t4_deployment/
# Follow deployment instructions in README
```

### Local Docker
```bash
docker build -t ip-assist-lite .
docker run -p 7862:7862 ip-assist-lite
```

## Support

- Check `docs/` for detailed documentation
- Review `tests/` for usage examples
- See `configs/` for configuration options

---

**Ready to build your custom medical knowledge base!** 🏥📚
